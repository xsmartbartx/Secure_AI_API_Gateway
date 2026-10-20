"""Regression tests for code-review findings on PR 3 (each test names the finding)."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import asyncio
import sqlite3
import threading

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import deps, providers
from app.config import settings
from app.db import Base, Organization, ProviderConnection, RequestLog, SessionLocal, engine
from app.errors import GatewayError
from app.main import app
from app.routers import control, data

OWNER = {"x-dev-org": "org_r", "x-dev-user": "owner"}
BODY = {"messages": [{"role": "user", "content": "hello"}]}


@pytest.fixture(autouse=True)
async def fresh(monkeypatch):
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(settings, "MOCK_PROVIDER_CHECK", True)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def gw_key(client):
    return {"authorization": "Bearer " + (await client.post("/api/keys", json={"name": "k"}, headers=OWNER)).json()["secret"]}


# --- billing.py: an empty webhook secret must not make forged events verifiable ---
async def test_stripe_webhook_refuses_everything_without_a_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    r = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=anything"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "webhook_not_configured"


def test_prod_with_billing_requires_the_webhook_secret(monkeypatch):
    from app.main import check_production_settings
    for k, v in dict(ENV="prod", AUTH_JWKS_URL="https://x/jwks", AUTH_ISSUER="https://x", REDIS_URL="redis://x",
                     CREDENTIAL_ENCRYPTION_KEY="k", STRIPE_SECRET_KEY="sk_live_x", STRIPE_WEBHOOK_SECRET="").items():
        monkeypatch.setattr(settings, k, v)
    with pytest.raises(RuntimeError, match="STRIPE_WEBHOOK_SECRET"):
        check_production_settings()
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_x")
    check_production_settings()


# --- control.py: spreadsheet formula injection past leading whitespace or newlines ---
@pytest.mark.parametrize("cell", [" =1+1", "  @SUM(A1)", "\n=cmd", "\t=cmd", "\r-1", " +1"])
def test_csv_neutralises_formulas_after_whitespace(cell):
    assert control._csv_cell(cell).startswith("'"), repr(cell)


@pytest.mark.parametrize("cell", ["plain", "mock-1", "a=b", "x -1"])
def test_csv_leaves_normal_text_alone(cell):
    assert control._csv_cell(cell) == cell


# --- deps.py: the blocking JWKS fetch must not run on the event loop ---
async def test_jwt_verification_runs_in_a_worker_thread(client, monkeypatch):
    seen = {}
    main_thread = threading.get_ident()

    def fake_verify(token):
        seen["thread"] = threading.get_ident()
        return {"sub": "u1", "iss": "x"}
    monkeypatch.setattr(deps, "_verify_jwt", fake_verify)
    monkeypatch.setattr(settings, "DEV_AUTH", False)
    r = await client.get("/api/me", headers={"authorization": "Bearer abc"})
    assert r.status_code == 200
    assert seen["thread"] != main_thread


def test_jwks_client_has_a_short_timeout(monkeypatch):
    captured = {}

    class Fake:
        def __init__(self, uri, **kw): captured.update(kw)
    monkeypatch.setattr(deps.jwt, "PyJWKClient", Fake)
    monkeypatch.setattr(deps, "_jwks", None)
    monkeypatch.setattr(settings, "AUTH_JWKS_URL", "https://x/jwks")
    deps._jwks_client()
    assert captured["timeout"] <= 10


# --- data.py: concurrent calls must not overshoot the monthly quota ---
async def test_concurrent_calls_cannot_exceed_the_quota(client):
    h = await gw_key(client)
    await client.post("/api/keys", json={"name": "x"}, headers=OWNER)
    async with SessionLocal() as s:
        org = (await s.execute(select(Organization))).scalar_one()
        org.monthly_call_quota = 3
        await s.commit()
    codes = [r.status_code for r in await asyncio.gather(*[client.post("/v1/chat", json=BODY, headers=h) for _ in range(12)])]
    assert codes.count(200) <= 3, codes
    assert codes.count(200) >= 1
    assert set(codes) <= {200, 429}
    async with SessionLocal() as s:
        rows = (await s.execute(select(RequestLog.decision))).scalars().all()
    assert "pending" not in rows  # every reserved call was settled


# --- data.py: an upstream that breaks in an unexpected way must not count as a successful call ---
async def test_unexpected_adapter_failure_is_an_error_not_a_billed_success(client, monkeypatch):
    async def broken(self, request, credential=None):
        return {"choices": None}["choices"][0]  # TypeError, not a GatewayError
    monkeypatch.setattr(type(data.ADAPTERS["mock"]), "execute_chat", broken)
    h = await gw_key(client)
    r = await client.post("/v1/chat", json=BODY, headers=h)
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "upstream_invalid_response"
    async with SessionLocal() as s:
        row = (await s.execute(select(RequestLog))).scalar_one()
    assert row.decision == "error"
    assert row.status_code == 502


async def test_unexpected_failure_mid_stream_is_reported_in_band(client, monkeypatch):
    from app.schemas import StreamEvent

    async def broken(self, request, credential=None):
        yield StreamEvent(type="delta", text="partial")
        raise KeyError("surprise")
    monkeypatch.setattr(type(data.ADAPTERS["mock"]), "stream_chat", broken)
    r = await client.post("/v1/chat", json={**BODY, "stream": True}, headers=await gw_key(client))
    assert r.status_code == 200
    assert "upstream_invalid_response" in r.text
    assert "[DONE]" not in r.text
    async with SessionLocal() as s:
        row = (await s.execute(select(RequestLog))).scalar_one()
    assert row.decision == "error"


# --- providers: unreadable stored credential, and concurrent adds ---
async def test_unreadable_stored_key_gives_a_clear_error_and_flags_the_connection(client, monkeypatch):
    t = httpx.MockTransport(lambda r: httpx.Response(200, json={"data": []}))
    monkeypatch.setattr(providers, "TRANSPORT", t)
    c = (await client.post("/api/providers", json={"provider": "anthropic", "label": "p", "api_key": "sk-ant-0123456789abcd"}, headers=OWNER)).json()
    async with SessionLocal() as s:
        row = await s.get(ProviderConnection, c["id"])
        row.credential_enc = row.credential_enc[:-1] + bytes([row.credential_enc[-1] ^ 1])  # corrupted or encrypted under another key
        await s.commit()
    r = await client.post("/v1/chat", json=BODY, headers=await gw_key(client))
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "provider_credentials_unreadable"
    assert "Providers" in r.json()["error"]["message"]
    assert (await client.get("/api/providers", headers=OWNER)).json()["items"][0]["status"] == "failing"


async def test_concurrent_adds_leave_exactly_one_default_and_respect_the_cap(client, monkeypatch):
    monkeypatch.setattr(providers, "TRANSPORT", httpx.MockTransport(lambda r: httpx.Response(200, json={"data": []})))

    async def allow_all(key, limit):  # the per-minute verification limit is not what is under test here
        return True, 0
    monkeypatch.setattr("app.routers.providers.limiter.allow", allow_all)
    add = lambda i: client.post("/api/providers", json={"provider": "openai", "label": f"c{i}", "api_key": f"sk-proj-{i:04d}-0123456789"}, headers=OWNER)
    rs = await asyncio.gather(*[add(i) for i in range(4)])
    assert [r.status_code for r in rs] == [201] * 4
    items = (await client.get("/api/providers", headers=OWNER)).json()["items"]
    assert [i["is_default"] for i in items].count(True) == 1

    rs = await asyncio.gather(*[add(i) for i in range(10, 22)])
    assert len((await client.get("/api/providers", headers=OWNER)).json()["items"]) <= 10
    assert {r.status_code for r in rs} <= {201, 409}


# --- migration: duplicate members must be removed before the unique constraint is added ---
def test_member_dedupe_keeps_the_earliest_row_per_user():
    import importlib.util, pathlib
    path = next(pathlib.Path("migrations/versions").glob("c898fd71f0f6_*.py"))
    spec = importlib.util.spec_from_file_location("mig", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    db = sqlite3.connect(":memory:")
    db.execute("create table members (id text primary key, org_id text, external_user_id text, created_at text)")
    db.executemany("insert into members values (?,?,?,?)", [
        ("a", "o1", "u1", "2026-01-02"), ("b", "o1", "u1", "2026-01-01"), ("c", "o1", "u1", "2026-01-03"),
        ("d", "o1", "u2", "2026-01-01"), ("e", "o2", "u1", "2026-01-05")])
    db.execute(mig.DEDUPE_MEMBERS_SQL)
    assert sorted(r[0] for r in db.execute("select id from members")) == ["b", "d", "e"]
