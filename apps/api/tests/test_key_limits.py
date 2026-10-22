import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import asyncio
import datetime as dt
import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app import alerts
from app.config import settings
from app.db import AlertSent, Base, Organization, RequestLog, SessionLocal, UsageDaily, engine
from app.main import app
from app.retention import purge_expired

OWNER = {"x-dev-org": "org_lim", "x-dev-user": "owner"}
ADMIN = {"x-dev-org": "org_lim", "x-dev-user": "adm", "x-dev-role": "admin"}
DEV = {"x-dev-org": "org_lim", "x-dev-user": "dev", "x-dev-role": "developer"}
OTHER = {"x-dev-org": "org_lim2", "x-dev-user": "o"}
BODY = {"messages": [{"role": "user", "content": "hello"}]}


@pytest.fixture(autouse=True)
async def fresh():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def new_key(client, headers=OWNER, **limits):
    r = await client.post("/api/keys", json={"name": "k", "rpm_limit": 1000, **limits}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def auth(k):
    return {"authorization": "Bearer " + k["secret"]}


async def call(client, k, **extra):
    return await client.post("/v1/chat", json={**BODY, **extra}, headers=auth(k))


async def set_quota(n):
    async with SessionLocal() as s:
        o = (await s.execute(select(Organization))).scalar_one()
        o.monthly_call_quota = n
        await s.commit()


# ---------- limits ----------
async def test_limits_default_to_none_and_are_shown_with_usage(client):
    k = await new_key(client)
    assert k["monthly_call_limit"] is None
    assert k["monthly_token_limit"] is None
    await call(client, k)
    item = (await client.get("/api/keys", headers=OWNER)).json()["items"][0]
    assert item["month_calls"] == 1
    assert item["month_tokens"] > 0


async def test_call_limit_stops_the_key_and_leaves_others_alone(client):
    limited = await new_key(client, monthly_call_limit=2)
    free = await new_key(client)
    assert [(await call(client, limited)).status_code for _ in range(2)] == [200, 200]
    r = await call(client, limited)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "key_limit_reached"
    assert "call limit" in r.json()["error"]["message"]
    assert r.headers["retry-after"] == "3600"
    assert (await call(client, free)).status_code == 200


async def test_token_limit_stops_the_key(client):
    k = await new_key(client, monthly_token_limit=5)
    assert (await call(client, k)).status_code == 200          # the mock reports about six tokens for this call, so the next one is over
    r = await call(client, k)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "key_limit_reached"
    assert "token limit" in r.json()["error"]["message"]


async def test_concurrent_calls_cannot_overshoot_a_key_limit(client):
    k = await new_key(client, monthly_call_limit=3)
    codes = [r.status_code for r in await asyncio.gather(*[call(client, k) for _ in range(12)])]
    assert codes.count(200) == 3, codes
    assert set(codes) <= {200, 429}


async def test_failed_and_blocked_calls_do_not_use_the_limit(client):
    k = await new_key(client, monthly_call_limit=2)
    await client.put("/api/policies/model_allow", json={"mode": "enforce", "models": ["mock-1"]}, headers=OWNER)
    for _ in range(4):
        assert (await call(client, k, model="nope")).status_code == 403
    assert (await call(client, k)).status_code == 200
    assert (await call(client, k)).status_code == 200
    assert (await call(client, k)).status_code == 429


async def test_streaming_obeys_the_limit(client):
    k = await new_key(client, monthly_call_limit=1)
    assert (await call(client, k, stream=True)).status_code == 200
    r = await call(client, k, stream=True)
    assert r.status_code == 429
    assert r.headers["content-type"].startswith("application/json")


async def test_usage_survives_log_retention(client):
    k = await new_key(client, monthly_call_limit=3)
    for _ in range(2):
        await call(client, k)
    now = dt.datetime.now(dt.timezone.utc)
    first = now.replace(day=1, hour=1, minute=0)
    async with SessionLocal() as s:                      # push this month's logs far enough back to be purged and rolled up
        for r in (await s.execute(select(RequestLog))).scalars():
            r.ts = first
        await s.commit()
    await purge_expired(now + dt.timedelta(days=40))     # a purge run "later" rolls them up, then they are gone from request_logs
    async with SessionLocal() as s:
        assert (await s.execute(select(func.count()).select_from(RequestLog))).scalar_one() == 0
        assert (await s.execute(select(func.sum(UsageDaily.billable)))).scalar_one() == 2
    item = (await client.get("/api/keys", headers=OWNER)).json()["items"][0]
    assert item["month_calls"] == 2                      # still counted for the month
    assert (await call(client, k)).status_code == 200
    assert (await call(client, k)).status_code == 429


async def test_patch_sets_clears_and_validates(client):
    k = await new_key(client)
    r = await client.patch(f"/api/keys/{k['id']}", json={"monthly_call_limit": 5, "monthly_token_limit": 1000}, headers=OWNER)
    assert r.status_code == 200
    assert (r.json()["monthly_call_limit"], r.json()["monthly_token_limit"]) == (5, 1000)
    r = await client.patch(f"/api/keys/{k['id']}", json={"monthly_call_limit": None}, headers=OWNER)   # null clears one, the other stays
    assert (r.json()["monthly_call_limit"], r.json()["monthly_token_limit"]) == (None, 1000)
    assert (await client.patch(f"/api/keys/{k['id']}", json={}, headers=OWNER)).status_code == 422
    assert (await client.patch(f"/api/keys/{k['id']}", json={"monthly_call_limit": 0}, headers=OWNER)).status_code == 422
    assert (await client.patch(f"/api/keys/{k['id']}", json={"monthly_call_limit": 10**10}, headers=OWNER)).status_code == 422
    assert (await client.post("/api/keys", json={"name": "x", "monthly_call_limit": -1}, headers=OWNER)).status_code == 422
    assert (await client.patch("/api/keys/nope", json={"monthly_call_limit": 1}, headers=OWNER)).status_code == 404


async def test_patch_roles_and_isolation(client):
    k = await new_key(client)
    await client.get("/api/me", headers=ADMIN)
    await client.get("/api/me", headers=DEV)
    assert (await client.patch(f"/api/keys/{k['id']}", json={"monthly_call_limit": 5}, headers=ADMIN)).status_code == 200
    assert (await client.patch(f"/api/keys/{k['id']}", json={"monthly_call_limit": 5}, headers=DEV)).status_code == 403
    assert (await client.patch(f"/api/keys/{k['id']}", json={"monthly_call_limit": 5}, headers=OTHER)).status_code == 404


async def test_rotating_a_key_keeps_its_limits(client):
    k = await new_key(client, monthly_call_limit=7, monthly_token_limit=900)
    new = (await client.post(f"/api/keys/{k['id']}/rotate", headers=OWNER)).json()
    assert (new["monthly_call_limit"], new["monthly_token_limit"]) == (7, 900)


async def test_the_playground_has_no_key_limit(client):
    await new_key(client, monthly_call_limit=1)
    for _ in range(3):
        assert (await client.post("/api/playground", json={"prompt": "hi"}, headers=OWNER)).status_code == 200


# ---------- alerts ----------
sent: list[dict] = []


@pytest.fixture
def mail(monkeypatch):
    sent.clear()

    def handler(request: httpx.Request):
        sent.append({"auth": request.headers["authorization"], **json.loads(request.content)})
        return httpx.Response(200, json={"id": "email_1"})
    monkeypatch.setattr(alerts, "TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(settings, "ALERT_FROM_EMAIL", "NEXORA Gateway <alerts@example.com>")


async def team(client):
    for h in (OWNER, ADMIN, DEV):
        await client.get("/api/me", headers=h)
    return (await client.get("/api/me", headers=OWNER)).json()["org"]["id"]


async def test_alert_at_80_percent_goes_to_owners_and_admins_once(client, mail):
    org = await team(client)
    await alerts.maybe_alert(org, 79, 100)
    assert sent == []
    await alerts.maybe_alert(org, 80, 100)
    assert len(sent) == 1
    m = sent[0]
    assert m["auth"] == "Bearer re_test_key"
    assert sorted(m["to"]) == ["adm@dev.local", "owner@dev.local"]            # not the developer
    assert m["from"] == "NEXORA Gateway <alerts@example.com>"
    assert "80%" in m["subject"]
    assert "80 of 100" in m["text"]
    assert "/app/billing" in m["text"]
    await alerts.maybe_alert(org, 90, 100)                                      # already told this month
    assert len(sent) == 1


async def test_100_percent_is_a_separate_alert(client, mail):
    org = await team(client)
    await alerts.maybe_alert(org, 100, 100)
    assert len(sent) == 2                                                         # crossing 100 also crosses 80
    assert any("100%" in m["subject"] for m in sent)
    await alerts.maybe_alert(org, 100, 100)
    assert len(sent) == 2


async def test_no_email_without_a_provider_key_but_the_claim_is_not_burned(client, mail, monkeypatch):
    org = await team(client)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    await alerts.maybe_alert(org, 90, 100)
    assert sent == []
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")             # configured later: the alert can still go out
    await alerts.maybe_alert(org, 90, 100)
    assert len(sent) == 1


async def test_members_without_an_email_are_skipped_and_failure_does_not_raise(client, mail, monkeypatch):
    org = await team(client)
    async with SessionLocal() as s:
        from app.db import Member
        for m in (await s.execute(select(Member))).scalars():
            m.email = ""
        await s.commit()
    await alerts.maybe_alert(org, 85, 100)
    assert sent == []

    async with SessionLocal() as s:
        from app.db import Member
        (await s.execute(select(Member).where(Member.external_user_id == "owner"))).scalar_one().email = "owner@dev.local"
        await s.commit()
    monkeypatch.setattr(alerts, "TRANSPORT", httpx.MockTransport(lambda r: httpx.Response(500)))
    await alerts.maybe_alert(org, 85, 100)                                      # provider down: logged, never raised


async def test_a_real_call_crossing_the_threshold_triggers_the_alert(client, mail):
    await team(client)
    k = await new_key(client)
    await set_quota(5)
    for _ in range(4):
        await call(client, k)
    await asyncio.sleep(0.2)                                                      # the alert is sent in the background
    assert len(sent) == 1
    assert "80%" in sent[0]["subject"]
    async with SessionLocal() as s:
        assert (await s.execute(select(func.count()).select_from(AlertSent))).scalar_one() == 1


async def test_me_reports_usage_for_the_dashboard_banner(client):
    k = await new_key(client)
    await set_quota(10)
    for _ in range(3):
        await call(client, k)
    assert (await client.get("/api/me", headers=OWNER)).json()["usage"] == {"used": 3, "limit": 10}


async def test_alert_claims_are_deleted_with_the_org_and_per_month(client, mail):
    org = await team(client)
    await alerts.maybe_alert(org, 90, 100)
    await client.post("/api/org/delete", json={"confirm": "org_lim"}, headers=OWNER)
    async with SessionLocal() as s:
        assert (await s.execute(select(func.count()).select_from(AlertSent))).scalar_one() == 0
