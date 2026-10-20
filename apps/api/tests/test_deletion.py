import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import base64
import datetime as dt
import hashlib
import hmac
import json
import time

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.config import settings
from app.db import (ApiKey, Base, Member, Organization, RequestLog, SecurityEvent, SessionLocal, StripeEvent,
                    Subscription, UsageDaily, engine)
from app.main import app
from app.routers import billing

OWNER = {"x-dev-org": "org_d", "x-dev-user": "owner"}
OTHER = {"x-dev-org": "org_keep", "x-dev-user": "keeper"}
SECRET = "whsec_" + base64.b64encode(b"test-signing-secret-bytes").decode()


@pytest.fixture(autouse=True)
async def fresh(monkeypatch):
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(settings, "ACCOUNT_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def populate(client, headers):
    k = (await client.post("/api/keys", json={"name": "k"}, headers=headers)).json()
    await client.post("/v1/chat", json={"messages": [{"role": "user", "content": "x"}]}, headers={"authorization": f"Bearer {k['secret']}"})
    me = (await client.get("/api/me", headers=headers)).json()
    org = me["org"]["id"]
    async with SessionLocal() as s:
        log = (await s.execute(select(RequestLog).where(RequestLog.org_id == org))).scalars().first()
        s.add(SecurityEvent(org_id=org, log_id=log.id, type="prompt_injection", severity="high"))
        s.add(UsageDaily(org_id=org, day=dt.date(2026, 9, 1), key_id=k["id"], model="m", calls=3, billable=3))
        s.add(Subscription(org_id=org, stripe_customer_id=f"cus_{org[:6]}", stripe_subscription_id=f"sub_{org[:6]}", plan="starter", status="active"))
        await s.commit()
    return org, k


async def rows(org):
    out = {}
    async with SessionLocal() as s:
        for m in (ApiKey, Member, RequestLog, SecurityEvent, UsageDaily, Subscription):
            out[m.__tablename__] = (await s.execute(select(func.count()).select_from(m).where(m.org_id == org))).scalar_one()
        out["org"] = (await s.execute(select(func.count()).select_from(Organization).where(Organization.id == org))).scalar_one()
    return out


async def test_delete_org_removes_everything(client):
    org, k = await populate(client, OWNER)
    keep, _ = await populate(client, OTHER)
    before = await rows(org)
    assert all(v >= 1 for v in before.values()), before
    r = await client.post("/api/org/delete", json={"confirm": "org_d"}, headers=OWNER)
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert all(v == 0 for v in (await rows(org)).values())
    assert all(v >= 1 for v in (await rows(keep)).values())  # other org untouched
    # the deleted org's key no longer works
    r = await client.post("/v1/chat", json={"messages": [{"role": "user", "content": "x"}]}, headers={"authorization": f"Bearer {k['secret']}"})
    assert r.status_code == 401


async def test_confirmation_must_match_name(client):
    org, _ = await populate(client, OWNER)
    for body in ({"confirm": "wrong"}, {"confirm": ""}, {}):
        assert (await client.post("/api/org/delete", json=body, headers=OWNER)).status_code == 422
    assert (await rows(org))["org"] == 1


async def test_only_owner_can_delete(client):
    org, _ = await populate(client, OWNER)
    admin = {"x-dev-org": "org_d", "x-dev-user": "adm", "x-dev-role": "admin"}
    r = await client.post("/api/org/delete", json={"confirm": "org_d"}, headers=admin)
    assert r.status_code == 403
    assert (await rows(org))["org"] == 1


async def test_stripe_subscription_cancelled_first_and_failure_aborts(client, monkeypatch):
    org, _ = await populate(client, OWNER)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    cancelled = []
    monkeypatch.setattr(billing.stripe.Subscription, "cancel", staticmethod(lambda sid, **kw: cancelled.append(sid)))
    assert (await client.post("/api/org/delete", json={"confirm": "org_d"}, headers=OWNER)).status_code == 200
    assert cancelled == [f"sub_{org[:6]}"]

    org2, _ = await populate(client, OTHER)
    def boom(sid, **kw): raise RuntimeError("stripe down")
    monkeypatch.setattr(billing.stripe.Subscription, "cancel", staticmethod(boom))
    r = await client.post("/api/org/delete", json={"confirm": "org_keep"}, headers=OTHER)
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "billing_cancel_failed"
    assert (await rows(org2))["org"] == 1  # nothing deleted while billing may still be running


async def test_leave_removes_membership_but_not_last_member(client):
    await populate(client, OWNER)
    second = {"x-dev-org": "org_d", "x-dev-user": "second", "x-dev-role": "developer"}
    await client.get("/api/me", headers=second)
    assert (await client.delete("/api/me", headers=OWNER)).status_code == 409  # sole owner with others present
    assert (await client.delete("/api/me", headers=second)).status_code == 200
    async with SessionLocal() as s:
        assert (await s.execute(select(Member).where(Member.external_user_id == "second"))).scalar_one_or_none() is None
    assert (await client.delete("/api/me", headers=OWNER)).status_code == 409  # last member: delete the org instead


# ---- NEXORA account webhooks (Svix-signed) ----
def signed(payload: dict, ts=None, secret=SECRET, msg_id="msg_1"):
    body = json.dumps(payload).encode()
    ts = str(ts or int(time.time()))
    key = base64.b64decode(secret.removeprefix("whsec_"))
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return body, {"svix-id": msg_id, "svix-timestamp": ts, "svix-signature": f"v1,{sig}", "content-type": "application/json"}


async def test_webhook_rejects_bad_or_stale_signatures(client):
    body, h = signed({"type": "user.deleted", "data": {"id": "u"}})
    assert (await client.post("/webhooks/account", content=body, headers={**h, "svix-signature": "v1,AAAA"})).status_code == 400
    body, h = signed({"type": "user.deleted", "data": {"id": "u"}}, ts=int(time.time()) - 3600)
    assert (await client.post("/webhooks/account", content=body, headers=h)).status_code == 400
    body, h = signed({"type": "user.deleted", "data": {"id": "u"}}, secret="whsec_" + base64.b64encode(b"other").decode())
    assert (await client.post("/webhooks/account", content=body, headers=h)).status_code == 400


async def test_webhook_unconfigured_is_refused(client, monkeypatch):
    monkeypatch.setattr(settings, "ACCOUNT_WEBHOOK_SECRET", "")
    body, h = signed({"type": "user.deleted", "data": {"id": "u"}})
    assert (await client.post("/webhooks/account", content=body, headers=h)).status_code == 503


async def test_user_deleted_removes_membership_and_personal_workspace(client):
    # personal workspace: org keyed by the user id
    personal = {"x-dev-org": "user_gone", "x-dev-user": "user_gone"}
    porg, _ = await populate(client, personal)
    # shared org with two members; deleting one user keeps the org
    shared_owner = {"x-dev-org": "org_shared", "x-dev-user": "stays"}
    sorg, _ = await populate(client, shared_owner)
    await client.get("/api/me", headers={"x-dev-org": "org_shared", "x-dev-user": "user_gone", "x-dev-role": "developer"})
    body, h = signed({"type": "user.deleted", "data": {"id": "user_gone", "deleted": True}})
    assert (await client.post("/webhooks/account", content=body, headers=h)).status_code == 200
    assert all(v == 0 for v in (await rows(porg)).values())
    r = await rows(sorg)
    assert r["org"] == 1
    assert r["members"] == 1
    assert r["api_keys"] == 1
    body, h = signed({"type": "user.deleted", "data": {"id": "user_gone"}}, msg_id="msg_2")
    assert (await client.post("/webhooks/account", content=body, headers=h)).status_code == 200  # idempotent


async def test_organization_deleted_removes_org(client):
    org, _ = await populate(client, OWNER)
    body, h = signed({"type": "organization.deleted", "data": {"id": "org_d", "deleted": True}})
    assert (await client.post("/webhooks/account", content=body, headers=h)).status_code == 200
    assert all(v == 0 for v in (await rows(org)).values())


async def test_unknown_event_is_acknowledged(client):
    body, h = signed({"type": "session.created", "data": {"id": "s"}})
    assert (await client.post("/webhooks/account", content=body, headers=h)).status_code == 200
