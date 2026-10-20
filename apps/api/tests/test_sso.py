import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")

import time
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from app import deps
from app.config import settings
from app.db import Base, engine
from app.main import app

ISS = "https://clerk.example.test"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJWKS:
    def get_signing_key_from_jwt(self, token):
        class K: key = KEY.public_key()
        return K


@pytest.fixture(autouse=True)
async def setup(monkeypatch):
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(deps, "_jwks_client", lambda: FakeJWKS())
    monkeypatch.setattr(settings, "AUTH_ISSUER", ISS)
    monkeypatch.setattr(settings, "AUTH_JWKS_URL", ISS + "/.well-known/jwks.json")
    monkeypatch.setattr(settings, "DEV_AUTH", False)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


def token(**over):
    now = int(time.time())
    claims = {"iss": ISS, "sub": "user_1", "iat": now, "nbf": now, "exp": now + 60, "azp": "http://localhost:3000", **over}
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, KEY, algorithm="RS256")


def bearer(**over):
    return {"authorization": f"Bearer {token(**over)}"}


async def test_valid_token_provisions_org_and_owner(client):
    r = await client.get("/api/me", headers=bearer(org_id="org_x", org_role="org:member"))
    assert r.status_code == 200
    assert r.json()["member"]["role"] == "owner"  # first member of a new org


async def test_personal_workspace_when_no_org(client):
    r = await client.get("/api/me", headers=bearer())
    assert r.status_code == 200
    assert r.json()["org"]["name"] == "user_1"


async def test_clerk_v2_org_claim(client):
    await client.get("/api/me", headers=bearer(o={"id": "org_v2", "rol": "admin"}))
    r = await client.get("/api/me", headers=bearer(sub="user_2", o={"id": "org_v2", "rol": "admin"}))
    assert r.json()["member"]["role"] == "admin"


async def test_expired_token_rejected(client):
    r = await client.get("/api/me", headers=bearer(exp=int(time.time()) - 10))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_session"


async def test_wrong_issuer_rejected(client):
    r = await client.get("/api/me", headers=bearer(iss="https://evil.example"))
    assert r.status_code == 401


async def test_unexpected_origin_rejected(client):
    r = await client.get("/api/me", headers=bearer(azp="https://evil.example"))
    assert r.status_code == 401


async def test_unsigned_token_rejected(client):
    bad = jwt.encode({"iss": ISS, "sub": "u", "exp": int(time.time()) + 60}, "x" * 32, algorithm="HS256")
    r = await client.get("/api/me", headers={"authorization": f"Bearer {bad}"})
    assert r.status_code == 401


async def test_dev_headers_ignored_when_dev_auth_off(client):
    r = await client.get("/api/me", headers={"x-dev-org": "org_a"})
    assert r.status_code == 401


async def test_same_user_other_org_is_isolated(client):
    await client.post("/api/keys", json={"name": "k"}, headers=bearer(org_id="org_a"))
    r = await client.get("/api/keys", headers=bearer(org_id="org_b"))
    assert r.json()["items"] == []
