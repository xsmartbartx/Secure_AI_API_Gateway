import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import datetime as dt
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db import Base, RequestLog, SecurityEvent, SessionLocal, Subscription, UsageDaily, engine
from app.main import app

OWNER = {"x-dev-org": "org_x", "x-dev-user": "owner"}
DEV = {"x-dev-org": "org_x", "x-dev-user": "dev", "x-dev-role": "developer"}
OTHER = {"x-dev-org": "org_y", "x-dev-user": "other"}
PROVIDER_SECRET = "sk-ant-EXPORT-SECRET-1234567890"


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


async def populate(client, headers, n_logs=3):
    key = (await client.post("/api/keys", json={"name": "export-key"}, headers=headers)).json()
    await client.post("/api/providers", json={"provider": "anthropic", "label": "prod", "api_key": PROVIDER_SECRET}, headers=headers)
    org = (await client.get("/api/me", headers=headers)).json()["org"]["id"]
    async with SessionLocal() as s:
        now = dt.datetime.now(dt.timezone.utc)
        for i in range(n_logs):
            s.add(RequestLog(org_id=org, key_id=key["id"], request_id=f"req_{i}", ts=now - dt.timedelta(minutes=i), provider="mock", model="m",
                             status_code=200, decision="allow", prompt_hash="hash" + str(i), tokens_in=1, tokens_out=2))
        await s.flush()
        first = (await s.execute(__import__("sqlalchemy").select(RequestLog).where(RequestLog.org_id == org).limit(1))).scalar_one()
        s.add(SecurityEvent(org_id=org, log_id=first.id, type="prompt_injection", severity="high", redacted_excerpt="…"))
        s.add(UsageDaily(org_id=org, day=dt.date(2026, 9, 1), key_id=key["id"], model="m", calls=5, billable=5))
        s.add(Subscription(org_id=org, stripe_customer_id=f"cus_{org[:8]}", stripe_subscription_id=f"sub_{org[:8]}", plan="starter", status="active"))
        await s.commit()
    return org, key


async def test_export_contains_everything_and_no_secrets(client):
    org, key = await populate(client, OWNER)
    r = await client.get("/api/org/export", headers=OWNER)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "attachment" in r.headers["content-disposition"]
    assert org in r.headers["content-disposition"]
    d = json.loads(r.text)  # must be one valid JSON document
    assert d["organization"]["name"] == "org_x"
    assert d["organization"]["plan"] == "free"
    assert [m["role"] for m in d["members"]] == ["owner"]
    assert d["members"][0]["email"].endswith("@dev.local")
    assert d["api_keys"][0]["name"] == "export-key"
    assert d["api_keys"][0]["last4"]
    assert d["provider_connections"][0]["label"] == "prod"
    assert d["provider_connections"][0]["hint"] == "…7890"
    assert len(d["request_logs"]) == 3
    assert {l["prompt_hash"] for l in d["request_logs"]} == {"hash0", "hash1", "hash2"}
    assert len(d["security_events"]) == 1
    assert d["usage_daily"][0]["calls"] == 5
    assert d["subscription"]["plan"] == "starter"
    assert d["generated_at"]
    assert d["notes"]
    # secrets and internals never leave
    for forbidden in (PROVIDER_SECRET, "key_hash", "credential_enc", key["secret"]):
        assert forbidden not in r.text, forbidden


async def test_export_is_valid_json_across_page_boundaries(client):
    await populate(client, OWNER, n_logs=2503)
    d = json.loads((await client.get("/api/org/export", headers=OWNER)).text)
    ids = [l["request_id"] for l in d["request_logs"]]
    assert len(ids) == 2503
    assert len(set(ids)) == 2503  # nothing dropped or duplicated between pages of 1000


async def test_export_of_an_empty_org_is_valid(client):
    await client.get("/api/me", headers=OWNER)
    d = json.loads((await client.get("/api/org/export", headers=OWNER)).text)
    assert d["request_logs"] == []
    assert d["api_keys"] == []
    assert d["subscription"] is None


async def test_only_admins_export_and_orgs_are_isolated(client):
    await populate(client, OWNER)
    await client.get("/api/me", headers=DEV)
    assert (await client.get("/api/org/export", headers=DEV)).status_code == 403
    await populate(client, OTHER, n_logs=1)
    d = json.loads((await client.get("/api/org/export", headers=OTHER)).text)
    assert d["organization"]["name"] == "org_y"
    assert len(d["request_logs"]) == 1
    assert len(d["members"]) == 1
    assert (await client.get("/api/org/export")).status_code == 401


async def test_my_data_export_is_only_my_membership(client):
    await populate(client, OWNER)
    await client.get("/api/me", headers=DEV)
    d = (await client.get("/api/me/export", headers=DEV)).json()
    assert d["member"]["role"] == "developer"
    assert d["member"]["external_user_id"] == "dev"
    assert d["organization"]["name"] == "org_x"
    assert "owner@dev.local" not in json.dumps(d)  # other members' data is not included
    assert "api_keys" not in d
    assert "request_logs" not in d


async def test_export_is_rate_limited(client):
    await populate(client, OWNER, n_logs=1)
    codes = [(await client.get("/api/org/export", headers=OWNER)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
