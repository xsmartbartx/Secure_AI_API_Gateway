import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import datetime as dt
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db import Base, Policy, RequestLog, SecurityEvent, SessionLocal, engine
from app.main import app
from app.retention import purge_expired
from app.usage import billable_this_month

OWNER = {"x-dev-org": "org_pol", "x-dev-user": "owner"}
DEV = {"x-dev-org": "org_pol", "x-dev-user": "dev", "x-dev-role": "developer"}
OTHER = {"x-dev-org": "org_pol2", "x-dev-user": "other"}
URL = "/api/policies/model_allow"


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


async def gw_key(client, headers=OWNER):
    return {"authorization": "Bearer " + (await client.post("/api/keys", json={"name": "k"}, headers=headers)).json()["secret"]}


async def call(client, key, model=None, **extra):
    body = {"messages": [{"role": "user", "content": "hi"}], **extra}
    if model:
        body["model"] = model
    return await client.post("/v1/chat", json=body, headers=key)


async def put(client, mode, models, headers=OWNER):
    return await client.put(URL, json={"mode": mode, "models": models}, headers=headers)


async def rows():
    async with SessionLocal() as s:
        return (await s.execute(select(RequestLog).order_by(RequestLog.ts))).scalars().all()


async def events():
    async with SessionLocal() as s:
        return (await s.execute(select(SecurityEvent))).scalars().all()


async def test_default_policy_is_off_and_empty(client):
    d = (await client.get("/api/policies", headers=OWNER)).json()
    assert d["model_allow"] == {"mode": "off", "models": [], "version": 0}


async def test_validation(client):
    assert (await put(client, "sometimes", ["a"])).status_code == 422
    for mode in ("monitor", "enforce"):
        assert (await put(client, mode, [])).status_code == 422           # an empty enforced list would block every call
    assert (await put(client, "off", [])).status_code == 200              # but clearing while off is fine
    assert (await put(client, "enforce", ["ok-*", "bad pattern"])).status_code == 422
    assert (await put(client, "enforce", ["[abc]"])).status_code == 422   # no character classes
    assert (await put(client, "enforce", ["x" * 101])).status_code == 422
    assert (await put(client, "enforce", [f"m{i}" for i in range(51)])).status_code == 422
    assert (await put(client, "enforce", ["a*b*c*d*e*f*g"])).status_code == 422   # at most 5 wildcards
    assert (await client.put(URL, json={"mode": "enforce"}, headers=OWNER)).status_code == 422


async def test_patterns_are_normalised_and_versioned(client):
    r = (await put(client, "enforce", ["  Claude-*  ", "GPT-4o", "gpt-4o", "claude-*"])).json()
    assert r["models"] == ["claude-*", "gpt-4o"] and r["version"] == 1
    assert (await put(client, "monitor", ["gpt-4o"])).json()["version"] == 2


async def test_roles(client):
    await client.get("/api/me", headers=OWNER)
    assert (await put(client, "enforce", ["x"], DEV)).status_code == 403
    assert (await client.post(URL + "/test", json={"model": "x"}, headers=DEV)).status_code == 403
    assert (await client.get("/api/policies", headers=DEV)).status_code == 200


async def test_enforce_blocks_unlisted_models_before_anything_is_sent_upstream(client):
    await put(client, "enforce", ["mock-*", "gpt-4o"])
    k = await gw_key(client)
    ok = await call(client, k, "mock-1")
    assert ok.status_code == 200
    blocked = await call(client, k, "claude-opus-9")
    assert blocked.status_code == 403
    err = blocked.json()["error"]
    assert err["code"] == "model_not_allowed" and "claude-opus-9" in err["message"] and err["request_id"].startswith("req_")
    rs = await rows()
    assert [(r.model, r.decision, r.status_code) for r in rs] == [("mock-1", "allow", 200), ("claude-opus-9", "block", 403)]
    assert rs[1].tokens_in == 0 and rs[1].tokens_out == 0
    ev = await events()
    assert len(ev) == 1 and ev[0].type == "policy_denied" and ev[0].rule_id == "model_allow" and ev[0].log_id == rs[1].id


async def test_matching_rules(client):
    await put(client, "enforce", ["claude-*", "gpt-4o"])
    t = lambda m: client.post(URL + "/test", json={"model": m}, headers=OWNER)
    assert (await t("Claude-Sonnet-5-5")).json() == {"allowed": True, "matched": "claude-*", "mode": "enforce", "flagged": False}
    assert (await t("gpt-4o")).json()["allowed"] is True
    assert (await t("gpt-4o-mini")).json() == {"allowed": False, "matched": None, "mode": "enforce", "flagged": False}   # exact entries are exact
    assert (await t("x" * 500)).status_code == 422


async def test_the_default_model_is_checked_too(client):
    await put(client, "enforce", ["claude-*"])
    r = await call(client, await gw_key(client))               # no model sent: the mock default "mock-1" applies
    assert r.status_code == 403 and "mock-1" in r.json()["error"]["message"]


async def test_monitor_lets_calls_through_but_flags_them(client):
    await put(client, "monitor", ["gpt-4o"])
    k = await gw_key(client)
    assert (await call(client, k, "mock-1")).status_code == 200
    assert (await call(client, k, "gpt-4o", provider="mock")).status_code == 200
    rs = await rows()
    assert [(r.model, r.decision) for r in rs] == [("mock-1", "flag"), ("gpt-4o", "allow")]
    ev = await events()
    assert len(ev) == 1 and ev[0].type == "policy_would_deny" and ev[0].log_id == rs[0].id


async def test_off_allows_everything_and_records_nothing(client):
    await put(client, "enforce", ["gpt-4o"])
    await put(client, "off", ["gpt-4o"])
    assert (await call(client, await gw_key(client), "anything-goes")).status_code == 200
    assert await events() == []


async def test_streaming_is_checked_before_the_first_byte(client):
    await put(client, "enforce", ["gpt-4o"])
    k = await gw_key(client)
    r = await call(client, k, "mock-1", stream=True)
    assert r.status_code == 403 and r.headers["content-type"].startswith("application/json")
    await put(client, "monitor", ["gpt-4o"])
    r = await call(client, k, "mock-1", stream=True)
    assert r.status_code == 200 and "[DONE]" in r.text
    assert [x.decision for x in await rows()] == ["block", "flag"]


async def test_blocked_calls_do_not_use_the_quota(client):
    await put(client, "enforce", ["mock-1"])
    k = await gw_key(client)
    for _ in range(5):
        assert (await call(client, k, "nope")).status_code == 403
    org = (await client.get("/api/me", headers=OWNER)).json()["org"]["id"]
    assert await billable_this_month(org) == 0
    assert (await call(client, k, "mock-1")).status_code == 200
    assert await billable_this_month(org) == 1


async def test_blocks_show_up_in_overview_usage_and_rollups(client):
    await put(client, "enforce", ["mock-1"])
    k = await gw_key(client)
    await call(client, k, "nope")
    await call(client, k, "mock-1")
    assert (await client.get("/api/overview", headers=OWNER)).json()["blocked"] == 1
    assert (await client.get("/api/usage?group=model", headers=OWNER)).json()["totals"]["blocked"] == 1
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    async with SessionLocal() as s:  # an old blocked call is rolled up as not billable
        r = (await s.execute(select(RequestLog).where(RequestLog.decision == "block"))).scalar_one()
        r.ts = old
        await s.commit()
    await purge_expired()
    org = (await client.get("/api/me", headers=OWNER)).json()["org"]["id"]
    async with SessionLocal() as s:
        from app.db import UsageDaily
        u = (await s.execute(select(UsageDaily).where(UsageDaily.model == "nope"))).scalar_one()
    assert (u.calls, u.blocked, u.billable) == (1, 1, 0)


async def test_policies_are_per_org(client):
    await put(client, "enforce", ["gpt-4o"])
    assert (await call(client, await gw_key(client, OTHER), "mock-1")).status_code == 200


async def test_playground_obeys_the_policy(client):
    await put(client, "enforce", ["gpt-4o"])
    r = await client.post("/api/playground", json={"prompt": "hi"}, headers=OWNER)
    assert r.status_code == 403 and r.json()["error"]["code"] == "model_not_allowed"


async def test_deleted_with_the_org_and_included_in_the_export(client):
    await put(client, "enforce", ["gpt-4o"])
    d = json.loads((await client.get("/api/org/export", headers=OWNER)).text)
    assert d["policies"][0]["type"] == "model_allow" and d["policies"][0]["config"]["models"] == ["gpt-4o"]
    await client.post("/api/org/delete", json={"confirm": "org_pol"}, headers=OWNER)
    async with SessionLocal() as s:
        assert (await s.execute(select(func.count()).select_from(Policy))).scalar_one() == 0
