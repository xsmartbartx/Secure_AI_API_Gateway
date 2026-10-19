"""Regression tests for the second round of review findings on PR 3."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app import retention
from app.config import settings
from app.db import Base, Policy, RequestLog, SessionLocal, engine
from app.main import app
from app.routers import data, team

OWNER = {"x-dev-org": "org_r2", "x-dev-user": "owner"}
BODY = {"messages": [{"role": "user", "content": "one two three four five six seven eight"}]}


@pytest.fixture(autouse=True)
async def fresh():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def gw_key(client):
    return {"authorization": "Bearer " + (await client.post("/api/keys", json={"name": "k"}, headers=OWNER)).json()["secret"]}


async def last_log():
    async with SessionLocal() as s:
        return (await s.execute(select(RequestLog).order_by(RequestLog.ts.desc()))).scalars().first()


# --- retention.py: a call still running must never be mistaken for an abandoned one ---
def test_every_call_has_a_deadline_shorter_than_the_stale_threshold():
    assert data.MAX_STREAM_SECONDS + data.MAX_CALL_SECONDS < retention.STALE_PENDING_MINUTES * 60
    assert max(data.MAX_STREAM_SECONDS, data.MAX_CALL_SECONDS) * 1.5 <= retention.STALE_PENDING_MINUTES * 60


async def test_a_stream_that_runs_too_long_is_stopped_and_settled(client, monkeypatch):
    monkeypatch.setattr(data, "MAX_STREAM_SECONDS", 0.5)
    monkeypatch.setattr(settings, "MOCK_STREAM_DELAY_MS", 200)
    r = await client.post("/v1/chat", json={**BODY, "stream": True}, headers=await gw_key(client))
    assert r.status_code == 200
    assert "stream_timeout" in r.text
    assert "[DONE]" not in r.text
    row = await last_log()
    assert (row.decision, row.status_code) == ("error", 504)


async def test_a_non_streaming_call_has_a_deadline_too(client, monkeypatch):
    async def slow(self, request, credential=None):
        await asyncio.sleep(5)
    monkeypatch.setattr(type(data.ADAPTERS["mock"]), "execute_chat", slow)
    monkeypatch.setattr(data, "MAX_CALL_SECONDS", 0.2)
    r = await client.post("/v1/chat", json=BODY, headers=await gw_key(client))
    assert r.status_code == 504
    assert r.json()["error"]["code"] == "upstream_timeout"
    row = await last_log()
    assert (row.decision, row.status_code) == ("error", 504)


async def test_the_first_chunk_of_a_stream_has_the_same_deadline(client, monkeypatch):
    async def stuck(self, request, credential=None):
        await asyncio.sleep(5)
        yield None
    monkeypatch.setattr(type(data.ADAPTERS["mock"]), "stream_chat", stuck)
    monkeypatch.setattr(data, "MAX_CALL_SECONDS", 0.2)
    r = await client.post("/v1/chat", json={**BODY, "stream": True}, headers=await gw_key(client))
    assert r.status_code == 504
    assert r.json()["error"]["code"] == "upstream_timeout"


# --- policies.py: concurrent saves ---
async def put(client, models, headers=OWNER):
    return await client.put("/api/policies/model_allow", json={"mode": "monitor", "models": models}, headers=headers)


async def test_concurrent_first_saves_do_not_conflict_and_get_distinct_versions(client):
    rs = await asyncio.gather(*[put(client, [f"m{i}"]) for i in range(6)])
    assert [r.status_code for r in rs] == [200] * 6
    assert (await client.get("/api/policies", headers=OWNER)).json()["model_allow"]["version"] == 6
    async with SessionLocal() as s:
        assert len((await s.execute(select(Policy))).scalars().all()) == 1


async def test_concurrent_saves_on_an_existing_policy_increment_the_version_once_each(client):
    await put(client, ["first"])
    rs = await asyncio.gather(*[put(client, [f"m{i}"]) for i in range(8)])
    assert all(r.status_code == 200 for r in rs)
    assert (await client.get("/api/policies", headers=OWNER)).json()["model_allow"]["version"] == 9
    assert sorted(r.json()["version"] for r in rs) == list(range(2, 10))   # every save saw its own version


# --- policies.py: the dry run must describe what a call will do ---
async def test_dry_run_says_monitor_mode_lets_the_call_through(client):
    await put(client, ["gpt-4o"])
    d = (await client.post("/api/policies/model_allow/test", json={"model": "other"}, headers=OWNER)).json()
    assert d == {"allowed": True, "matched": None, "mode": "monitor", "flagged": True}
    d = (await client.post("/api/policies/model_allow/test", json={"model": "gpt-4o"}, headers=OWNER)).json()
    assert d["allowed"] is True
    assert d["flagged"] is False
    await client.put("/api/policies/model_allow", json={"mode": "enforce", "models": ["gpt-4o"]}, headers=OWNER)
    d = (await client.post("/api/policies/model_allow/test", json={"model": "other"}, headers=OWNER)).json()
    assert d["allowed"] is False
    assert d["flagged"] is False


# --- team.py: owner changes are serialised per organization ---
def test_member_changes_lock_the_organization_row_first():
    sql = str(team._lock_org_stmt("org-id").compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql
    assert "organizations" in sql


async def test_the_last_active_owner_guard_refuses_a_state_with_no_owner(client):
    await client.get("/api/me", headers=OWNER)
    async with SessionLocal() as s:
        from app.db import Member
        org_id = (await s.execute(select(Member.org_id))).scalar_one()
        owner = (await s.execute(select(Member))).scalar_one()
        owner.role = "viewer"          # the state another transaction could have committed
        await s.flush()
        with pytest.raises(Exception) as e:
            await team._ensure_active_owner(s, org_id)
        assert getattr(e.value, "code", "") == "last_owner"


# --- log hygiene (SonarCloud pythonsecurity:S5145, log injection) ---
def test_log_values_cannot_forge_lines():
    from app.logsafe import clean
    assert clean("org\nINFO fake line\r\tend") == "org?INFO fake line??end"
    assert clean("x" * 500) == "x" * 80
    assert clean(("a", "b")) == "('a', 'b')"


def test_logged_modes_come_from_the_closed_set():
    from app.logsafe import one_of
    assert one_of("enforce", ("off", "monitor", "enforce")) == "enforce"
    assert one_of("enforce\nINFO forged", ("off", "monitor", "enforce")) == "?"


async def test_a_policy_save_logs_only_known_values(client, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="gateway.policies")
    await put(client, ["gpt-4o"])
    line = next(r.getMessage() for r in caplog.records if r.name == "gateway.policies")
    assert "mode=monitor" in line
    assert "gpt-4o" not in line          # the patterns themselves are never logged, only how many
