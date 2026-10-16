import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_gateway.db"
os.environ["ENV"] = "dev"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import Base, engine
from app.main import app

DEV = {"x-dev-org": "org_a", "x-dev-user": "alice"}


@pytest.fixture(autouse=True)
async def fresh_db():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def make_key(client, headers=DEV, rpm=60):
    r = await client.post("/api/keys", json={"name": "t", "rpm_limit": rpm}, headers=headers)
    assert r.status_code == 201
    return r.json()


async def test_first_call_loop(client):
    k = await make_key(client)
    assert k["secret"].startswith("nx_live_")
    r = await client.post("/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]},
                          headers={"authorization": f"Bearer {k['secret']}"})
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"].startswith("[mock]")
    assert r.headers["x-nexora-request-id"].startswith("req_")
    logs = (await client.get("/api/logs", headers=DEV)).json()["items"]
    assert len(logs) == 1 and logs[0]["decision"] == "allow"
    keys = (await client.get("/api/keys", headers=DEV)).json()["items"]
    assert "secret" not in keys[0] and keys[0]["last_used_at"]


async def test_bad_key_envelope(client):
    r = await client.post("/v1/chat", json={"messages": [{"role": "user", "content": "x"}]},
                          headers={"authorization": "Bearer nx_live_nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_key"


async def test_revoked_key_rejected(client):
    k = await make_key(client)
    await client.post(f"/api/keys/{k['id']}/revoke", headers=DEV)
    r = await client.post("/v1/chat", json={"messages": [{"role": "user", "content": "x"}]},
                          headers={"authorization": f"Bearer {k['secret']}"})
    assert r.status_code == 401


async def test_rate_limit(client):
    k = await make_key(client, rpm=2)
    h = {"authorization": f"Bearer {k['secret']}"}
    body = {"messages": [{"role": "user", "content": "x"}]}
    codes = [(await client.post("/v1/chat", json=body, headers=h)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


async def test_org_isolation(client):
    k = await make_key(client)
    await client.post("/v1/chat", json={"messages": [{"role": "user", "content": "x"}]},
                      headers={"authorization": f"Bearer {k['secret']}"})
    other = {"x-dev-org": "org_b", "x-dev-user": "bob"}
    assert (await client.get("/api/logs", headers=other)).json()["items"] == []
    assert (await client.get("/api/keys", headers=other)).json()["items"] == []
    assert (await client.post(f"/api/keys/{k['id']}/revoke", headers=other)).status_code == 404


async def test_quota(client):
    k = await make_key(client)
    h = {"authorization": f"Bearer {k['secret']}"}
    body = {"messages": [{"role": "user", "content": "x"}]}
    from app.db import SessionLocal, Organization
    async with SessionLocal() as s:
        from sqlalchemy import select
        org = (await s.execute(select(Organization))).scalar_one()
        org.monthly_call_quota = 1
        await s.commit()
    assert (await client.post("/v1/chat", json=body, headers=h)).status_code == 200
    r = await client.post("/v1/chat", json=body, headers=h)
    assert r.status_code == 429 and r.json()["error"]["code"] == "quota_exceeded"


async def test_viewer_cannot_create_key(client):
    await make_key(client)  # alice becomes owner
    r = await client.post("/api/keys", json={"name": "x"}, headers={"x-dev-org": "org_a", "x-dev-user": "v", "x-dev-role": "viewer"})
    assert r.status_code == 403


async def test_openai_alias_and_validation(client):
    k = await make_key(client)
    h = {"authorization": f"Bearer {k['secret']}"}
    r = await client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "x"}]}, headers=h)
    assert r.json()["object"] == "chat.completion"
    r = await client.post("/v1/chat", json={"messages": []}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


async def test_playground_logs_without_key(client):
    r = await client.post("/api/playground", json={"prompt": "hello"}, headers=DEV)
    assert r.status_code == 200 and "[mock]" in r.json()["choices"][0]["message"]["content"]
    logs = (await client.get("/api/logs", headers=DEV)).json()["items"]
    assert len(logs) == 1 and logs[0]["key_id"] is None


# ---- billing / webhooks ----
import hashlib, hmac, json, time
from app.config import settings


def _signed(payload: dict, secret="whsec_test"):
    body = json.dumps(payload).encode()
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"stripe-signature": f"t={t},v1={sig}", "content-type": "application/json"}


async def test_webhook_rejects_bad_signature(client):
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    r = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=bad"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_signature"


async def test_webhook_upgrades_plan_and_is_idempotent(client):
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    await make_key(client)
    me = (await client.get("/api/me", headers=DEV)).json()
    ev = {"id": "evt_1", "object": "event", "type": "checkout.session.completed", "data": {"object": {
        "object": "checkout.session", "mode": "subscription", "client_reference_id": me["org"]["id"], "subscription": "sub_1"}}}
    body, h = _signed(ev)
    assert (await client.post("/webhooks/stripe", content=body, headers=h)).json() == {"received": True}
    assert (await client.get("/api/me", headers=DEV)).json()["org"]["quota"] == 1500
    body, h = _signed(ev)
    assert (await client.post("/webhooks/stripe", content=body, headers=h)).json()["duplicate"] is True


async def test_cancel_downgrades(client):
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    await make_key(client)
    org_id = (await client.get("/api/me", headers=DEV)).json()["org"]["id"]
    up = {"id": "evt_a", "object": "event", "type": "checkout.session.completed", "data": {"object": {"object": "checkout.session", "mode": "subscription", "client_reference_id": org_id, "subscription": "sub_1"}}}
    await client.post("/webhooks/stripe", content=_signed(up)[0], headers=_signed(up)[1])
    dele = {"id": "evt_b", "object": "event", "type": "customer.subscription.deleted", "data": {"object": {"object": "subscription", "id": "sub_1", "customer": "cus_x", "status": "canceled", "metadata": {"org_id": org_id}}}}
    b, h = _signed(dele)
    await client.post("/webhooks/stripe", content=b, headers=h)
    assert (await client.get("/api/me", headers=DEV)).json()["org"]["quota"] == 100


async def test_checkout_disabled_without_stripe(client):
    settings.STRIPE_SECRET_KEY = ""
    r = await client.post("/api/billing/checkout", headers=DEV)
    assert r.status_code == 503 and r.json()["error"]["code"] == "billing_disabled"


# ---- bugs found by replica-test (written failing first) ----
async def test_B1_blank_key_name_rejected(client):
    r = await client.post("/api/keys", json={"name": "   "}, headers=DEV)
    assert r.status_code == 422


async def test_B2_timestamps_are_utc_aware(client):
    k = await make_key(client)
    assert k["created_at"].endswith("Z") or "+00:00" in k["created_at"]
    await client.post("/v1/chat", json={"messages": [{"role": "user", "content": "x"}]}, headers={"authorization": f"Bearer {k['secret']}"})
    ts = (await client.get("/api/logs", headers=DEV)).json()["items"][0]["ts"]
    assert ts.endswith("Z") or "+00:00" in ts


async def test_B5_invalid_json_message(client):
    k = await make_key(client)
    r = await client.post("/v1/chat", content=b"nope", headers={"authorization": f"Bearer {k['secret']}", "content-type": "application/json"})
    assert r.status_code == 422 and r.json()["error"]["message"].startswith("Request body is not valid JSON")


# ---- found by the Playwright suite: the dashboard fires several requests at once on a user's first visit ----
async def test_B6_concurrent_first_requests_provision_one_org(client):
    import asyncio
    hdr = {"x-dev-org": "org_race", "x-dev-user": "racer"}
    rs = await asyncio.gather(*[client.get(p, headers=hdr) for p in ["/api/me", "/api/keys", "/api/overview", "/api/logs", "/api/me", "/api/usage"]])
    assert [r.status_code for r in rs] == [200] * 6, [r.text for r in rs if r.status_code != 200]
    from app.db import Member, Organization, SessionLocal
    from sqlalchemy import func, select
    async with SessionLocal() as s:
        assert (await s.execute(select(func.count()).select_from(Organization).where(Organization.external_org_id == "org_race"))).scalar_one() == 1
        assert (await s.execute(select(func.count()).select_from(Member).where(Member.external_user_id == "racer"))).scalar_one() == 1


async def test_B7_csv_filename_is_readable_by_the_browser(client):
    # the web app (gateway.onenexora.com) and the API (api.onenexora.com) are different origins: the filename header must be exposed
    r = await client.get("/api/usage?format=csv", headers={**DEV, "origin": "http://localhost:3000"})
    assert "content-disposition" in r.headers.get("access-control-expose-headers", "").lower()
