import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import json
import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app import providers
from app.config import settings
from app.db import Base, ProviderConnection, SessionLocal, engine
from app.main import app
from app.routers import data

OWNER = {"x-dev-org": "org_p", "x-dev-user": "owner"}
OTHER = {"x-dev-org": "org_q", "x-dev-user": "q"}
DEVELOPER = {"x-dev-org": "org_p", "x-dev-user": "dev", "x-dev-role": "developer"}
SECRET_A = "sk-ant-AAAA1111secretvalue"
SECRET_O = "sk-proj-OOOO2222secretvalue"

seen: list[tuple[str, str]] = []  # (url path, credential the upstream saw)


def cred_of(request: httpx.Request) -> str:
    return request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ")


def upstream(request: httpx.Request) -> httpx.Response:
    seen.append((request.url.path, cred_of(request)))
    if "bad" in cred_of(request):
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided: bad-****"}})
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": []})
    if "anthropic" in request.url.host:
        return httpx.Response(200, json={"id": "msg_1", "model": "claude-x", "content": [{"type": "text", "text": "hi from claude"}], "stop_reason": "end_turn", "usage": {"input_tokens": 3, "output_tokens": 4}})
    return httpx.Response(200, json={"id": "c_1", "model": "gpt-x", "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi from gpt"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 2, "completion_tokens": 5, "total_tokens": 7}})


@pytest.fixture(autouse=True)
async def fresh(monkeypatch):
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    seen.clear()
    t = httpx.MockTransport(upstream)
    monkeypatch.setattr(providers, "TRANSPORT", t)
    monkeypatch.setattr(data.ADAPTERS["anthropic"], "transport", t)
    monkeypatch.setattr(data.ADAPTERS["openai"], "transport", t)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def add(client, provider="anthropic", key=SECRET_A, label="main", headers=OWNER):
    return await client.post("/api/providers", json={"provider": provider, "label": label, "api_key": key}, headers=headers)


async def gw_key(client, headers=OWNER):
    return {"authorization": "Bearer " + (await client.post("/api/keys", json={"name": "k"}, headers=headers)).json()["secret"]}


BODY = {"messages": [{"role": "user", "content": "hello"}]}


async def test_add_validates_stores_encrypted_and_never_returns_the_key(client):
    r = await add(client)
    assert r.status_code == 201
    out = r.json()
    assert SECRET_A not in json.dumps(out) and out["hint"] == "…alue"
    assert out["is_default"] is True and out["status"] == "ok" and out["provider"] == "anthropic"
    assert (await client.get("/api/providers", headers=OWNER)).json()["items"][0].keys().isdisjoint({"api_key", "credential", "credential_enc"})
    assert SECRET_A not in (await client.get("/api/providers", headers=OWNER)).text
    # the database never holds the plaintext
    async with SessionLocal() as s:
        raw = (await s.execute(select(ProviderConnection))).scalar_one()
        assert SECRET_A.encode() not in raw.credential_enc and b"AAAA1111" not in raw.credential_enc
    assert ("/v1/models", SECRET_A) in seen  # it was verified against the provider


async def test_ciphertext_is_bound_to_its_row():
    blob = providers.encrypt_credential("sk-secret", aad="conn-1:org-1")
    assert providers.decrypt_credential(blob, aad="conn-1:org-1") == "sk-secret"
    with pytest.raises(Exception):
        providers.decrypt_credential(blob, aad="conn-2:org-1")  # moved to another row/org
    first = providers.encrypt_credential("sk-secret", aad="x")
    second = providers.encrypt_credential("sk-secret", aad="x")
    assert first != second  # a fresh nonce for every value


async def test_rejected_key_is_not_stored(client):
    r = await add(client, key="bad-key-123456")
    assert r.status_code == 422 and r.json()["error"]["code"] == "provider_rejected_key"
    assert "bad-key" not in r.text
    assert (await client.get("/api/providers", headers=OWNER)).json()["items"] == []


async def test_unreachable_provider_is_not_stored(client, monkeypatch):
    def down(request): raise httpx.ConnectError("boom")
    monkeypatch.setattr(providers, "TRANSPORT", httpx.MockTransport(down))
    r = await add(client)
    assert r.status_code == 502 and r.json()["error"]["code"] == "provider_unreachable"
    assert (await client.get("/api/providers", headers=OWNER)).json()["items"] == []


async def test_default_rules(client):
    a = (await add(client, "anthropic", SECRET_A, "a")).json()
    o = (await add(client, "openai", SECRET_O, "o")).json()
    assert a["is_default"] is True and o["is_default"] is False  # the first connection becomes the default
    assert (await client.post(f"/api/providers/{o['id']}/default", headers=OWNER)).status_code == 200
    items = {i["label"]: i for i in (await client.get("/api/providers", headers=OWNER)).json()["items"]}
    assert items["o"]["is_default"] and not items["a"]["is_default"]  # exactly one default
    assert (await client.delete(f"/api/providers/{o['id']}", headers=OWNER)).status_code == 200
    items = (await client.get("/api/providers", headers=OWNER)).json()["items"]
    assert [i["label"] for i in items] == ["a"]


async def test_roles_and_isolation(client):
    c = (await add(client)).json()
    assert (await add(client, headers=DEVELOPER)).status_code == 403                      # developers cannot add
    assert (await client.get("/api/providers", headers=DEVELOPER)).status_code == 200      # but can see what exists
    assert (await client.delete(f"/api/providers/{c['id']}", headers=DEVELOPER)).status_code == 403
    for method, path in (("delete", f"/api/providers/{c['id']}"), ("post", f"/api/providers/{c['id']}/test"), ("post", f"/api/providers/{c['id']}/default")):
        assert (await getattr(client, method)(path, headers=OTHER)).status_code == 404     # another org cannot touch it
    assert (await client.get("/api/providers", headers=OTHER)).json()["items"] == []


async def test_input_validation_and_cap(client):
    assert (await client.post("/api/providers", json={"provider": "nope", "label": "x", "api_key": "k" * 20}, headers=OWNER)).status_code == 422
    assert (await client.post("/api/providers", json={"provider": "openai", "label": " ", "api_key": "k" * 20}, headers=OWNER)).status_code == 422
    assert (await client.post("/api/providers", json={"provider": "openai", "label": "x", "api_key": "short"}, headers=OWNER)).status_code == 422
    for i in range(10):
        assert (await add(client, "openai", f"sk-proj-{i:04d}-xxxxxxxxxxxx", f"c{i}")).status_code == 201
    r = await add(client, "openai", "sk-proj-extra-xxxxxxxxxxxx", "c11")
    assert r.status_code == 409 and r.json()["error"]["code"] == "too_many_connections"


async def test_test_endpoint_updates_status(client, monkeypatch):
    c = (await add(client)).json()
    assert (await client.post(f"/api/providers/{c['id']}/test", headers=OWNER)).json()["status"] == "ok"
    monkeypatch.setattr(providers, "TRANSPORT", httpx.MockTransport(lambda r: httpx.Response(401, json={})))
    r = await client.post(f"/api/providers/{c['id']}/test", headers=OWNER)
    assert r.status_code == 200 and r.json()["status"] == "failing"
    assert (await client.get("/api/providers", headers=OWNER)).json()["items"][0]["status"] == "failing"


async def test_calls_use_the_orgs_own_key_and_others_do_not_get_it(client, monkeypatch):
    await add(client, "anthropic", SECRET_A)
    mine = await gw_key(client)
    r = await client.post("/v1/chat", json=BODY, headers=mine)
    assert r.status_code == 200 and r.json()["provider"] == "anthropic" and "hi from claude" in r.text
    assert ("/v1/messages", SECRET_A) in seen

    # another org without a connection never sees org_p's key; it falls back to the platform key when one exists
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-platform-shared")
    theirs = await gw_key(client, OTHER)
    r = await client.post("/v1/chat", json=BODY, headers=theirs)
    assert r.status_code == 200 and r.json()["provider"] == "openai"
    assert ("/v1/chat/completions", "sk-platform-shared") in seen
    assert all(c != SECRET_A for p, c in seen if p == "/v1/chat/completions")


async def test_requested_provider_picks_that_connection_and_streaming_uses_it(client):
    await add(client, "anthropic", SECRET_A, "a")
    await add(client, "openai", SECRET_O, "o")
    h = await gw_key(client)
    r = await client.post("/v1/chat", json={**BODY, "provider": "openai"}, headers=h)
    assert r.json()["provider"] == "openai" and ("/v1/chat/completions", SECRET_O) in seen
    # no provider in the request: the default connection (the first one added)
    assert (await client.post("/v1/chat", json=BODY, headers=h)).json()["provider"] == "anthropic"


async def test_provider_auth_failure_is_generic_and_flags_the_connection(client):
    c = (await add(client)).json()
    async with SessionLocal() as s:  # the key was revoked at the provider after it was saved
        from app.providers import encrypt_credential
        row = await s.get(ProviderConnection, c["id"])
        row.credential_enc = encrypt_credential("bad-revoked-key-0000", aad=f"{row.id}:{row.org_id}")
        await s.commit()
    r = await client.post("/v1/chat", json=BODY, headers=await gw_key(client))
    assert r.status_code == 502 and r.json()["error"]["code"] == "provider_auth_failed"
    assert "bad-" not in r.text and "Incorrect" not in r.text  # the provider's message may echo key fragments
    assert (await client.get("/api/providers", headers=OWNER)).json()["items"][0]["status"] == "failing"


async def test_no_provider_anywhere_points_to_the_providers_page(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_UPSTREAM", False)
    r = await client.post("/v1/chat", json=BODY, headers=await gw_key(client))
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_not_configured" and "Providers" in r.json()["error"]["message"]


async def test_deleting_the_org_deletes_its_credentials(client):
    await add(client)
    await client.post("/api/org/delete", json={"confirm": "org_p"}, headers=OWNER)
    async with SessionLocal() as s:
        assert (await s.execute(select(ProviderConnection))).first() is None


async def test_encryption_key_rules(monkeypatch):
    import base64
    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "ENV", "prod")
    with pytest.raises(RuntimeError):
        providers.encrypt_credential("x", aad="a")  # prod refuses to run with the dev key
    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"short").decode())
    with pytest.raises(RuntimeError):
        providers.encrypt_credential("x", aad="a")
    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    assert providers.decrypt_credential(providers.encrypt_credential("ok", aad="a"), aad="a") == "ok"
