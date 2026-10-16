import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import Base, engine
from app.main import app


def who(user, role="developer", org="org_t"):
    return {"x-dev-org": org, "x-dev-user": user, "x-dev-role": role}


OWNER = who("owner")           # first member of the org becomes its owner
ADMIN, DEV, VIEWER = who("adm", "admin"), who("dev"), who("vw", "viewer")


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


async def team(client):
    """owner, then an admin, a developer and a viewer join."""
    for h in (OWNER, ADMIN, DEV, VIEWER):
        await client.get("/api/me", headers=h)
    items = (await client.get("/api/members", headers=OWNER)).json()["items"]
    return {i["email"].split("@")[0]: i for i in items}


async def patch(client, headers, member, **body):
    return await client.patch(f"/api/members/{member['id']}", json=body, headers=headers)


async def test_everyone_can_list_members_and_sees_who_they_are(client):
    m = await team(client)
    assert set(m) == {"owner", "adm", "dev", "vw"} and m["owner"]["role"] == "owner" and m["adm"]["role"] == "admin"
    mine = (await client.get("/api/members", headers=VIEWER)).json()["items"]
    assert [i["email"] for i in mine if i["is_me"]] == ["vw@dev.local"]
    assert all(set(i) == {"id", "email", "role", "status", "created_at", "is_me"} for i in mine)  # no internal ids leak


async def test_owner_manages_everyone(client):
    m = await team(client)
    assert (await patch(client, OWNER, m["dev"], role="admin")).json()["role"] == "admin"
    assert (await patch(client, OWNER, m["dev"], role="owner")).json()["role"] == "owner"
    assert (await patch(client, OWNER, m["vw"], role="developer")).json()["role"] == "developer"


async def test_admin_can_only_manage_developers_and_viewers(client):
    m = await team(client)
    assert (await patch(client, ADMIN, m["vw"], role="developer")).status_code == 200
    assert (await patch(client, ADMIN, m["dev"], role="viewer")).status_code == 200
    assert (await patch(client, ADMIN, m["dev"], role="admin")).status_code == 403       # cannot grant admin
    assert (await patch(client, ADMIN, m["dev"], role="owner")).status_code == 403       # nor owner
    assert (await patch(client, ADMIN, m["owner"], role="viewer")).status_code == 403    # cannot touch an owner
    assert (await patch(client, ADMIN, m["owner"], status="suspended")).status_code == 403
    assert (await patch(client, DEV, m["vw"], role="developer")).status_code == 403      # developers cannot manage at all


async def test_nobody_edits_themselves(client):
    m = await team(client)
    assert (await patch(client, OWNER, m["owner"], role="viewer")).status_code == 409
    assert (await patch(client, ADMIN, m["adm"], status="suspended")).status_code == 409


async def test_there_is_always_an_active_owner(client):
    m = await team(client)
    await patch(client, OWNER, m["adm"], role="owner")                                    # two owners now
    assert (await patch(client, who("adm", "admin"), m["owner"], role="viewer")).status_code == 200
    # the remaining owner cannot be removed by anyone else, and cannot remove themselves
    assert (await patch(client, who("owner", "viewer"), m["adm"], status="suspended")).status_code == 403
    assert (await patch(client, who("adm", "admin"), m["adm"], role="viewer")).status_code == 409


async def test_suspended_member_is_locked_out_but_keeps_their_own_data_rights(client):
    m = await team(client)
    key = (await client.post("/api/keys", json={"name": "org key"}, headers=OWNER)).json()
    assert (await patch(client, OWNER, m["dev"], status="suspended")).json()["status"] == "suspended"
    r = await client.get("/api/keys", headers=DEV)
    assert r.status_code == 403 and r.json()["error"]["code"] == "member_suspended"
    assert (await client.post("/api/keys", json={"name": "x"}, headers=DEV)).status_code == 403
    assert (await client.get("/api/members", headers=DEV)).status_code == 403
    me = (await client.get("/api/me", headers=DEV)).json()           # the UI needs this to explain what happened
    assert me["member"]["status"] == "suspended"
    assert (await client.get("/api/me/export", headers=DEV)).status_code == 200   # data rights do not depend on suspension
    # suspending a person does not break the organization's API keys
    ok = await client.post("/v1/chat", json={"messages": [{"role": "user", "content": "x"}]}, headers={"authorization": "Bearer " + key["secret"]})
    assert ok.status_code == 200
    # signing in again does not un-suspend
    await client.get("/api/me", headers=DEV)
    assert (await client.get("/api/keys", headers=DEV)).status_code == 403
    # restore
    assert (await patch(client, OWNER, m["dev"], status="active")).json()["status"] == "active"
    assert (await client.get("/api/keys", headers=DEV)).status_code == 200


async def test_a_suspended_member_can_still_leave(client):
    m = await team(client)
    await patch(client, OWNER, m["dev"], status="suspended")
    assert (await client.delete("/api/me", headers=DEV)).status_code == 200


async def test_orgs_are_isolated(client):
    m = await team(client)
    outsider = who("boss", "owner", org="org_other")
    await client.get("/api/me", headers=outsider)
    assert (await patch(client, outsider, m["dev"], role="viewer")).status_code == 404
    assert [i["email"] for i in (await client.get("/api/members", headers=outsider)).json()["items"]] == ["boss@dev.local"]


async def test_validation(client):
    m = await team(client)
    assert (await patch(client, OWNER, m["dev"], role="superuser")).status_code == 422
    assert (await patch(client, OWNER, m["dev"], status="banned")).status_code == 422
    assert (await patch(client, OWNER, m["dev"])).status_code == 422                       # nothing to change
    assert (await client.patch("/api/members/nope", json={"role": "viewer"}, headers=OWNER)).status_code == 404
