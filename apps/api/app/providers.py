"""Customers' own model-provider keys: encryption at rest, verification against the provider, and choosing the upstream for a call."""
import base64
import hashlib
import logging
import os

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import ProviderConnection
from app.errors import GatewayError

log = logging.getLogger("gateway.providers")

PROVIDERS = ("anthropic", "openai")
TRANSPORT = None  # tests inject an httpx transport
_VERSION = b"\x01"

_CHECK = {  # cheapest authenticated read each provider offers: list models
    "anthropic": ("https://api.anthropic.com/v1/models", lambda k: {"x-api-key": k, "anthropic-version": "2023-06-01"}),
    "openai": ("https://api.openai.com/v1/models", lambda k: {"Authorization": f"Bearer {k}"}),
}


def _key() -> bytes:
    if settings.CREDENTIAL_ENCRYPTION_KEY:
        try:
            key = base64.b64decode(settings.CREDENTIAL_ENCRYPTION_KEY, validate=True)
        except ValueError:
            key = b""
        if len(key) != 32:
            raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY must be 32 random bytes, base64 encoded.")
        return key
    if settings.ENV == "prod":
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY is required when ENV=prod.")
    return hashlib.sha256(b"nexora-gateway-dev-only-key").digest()  # dev/tests only


def encrypt_credential(plain: str, aad: str) -> bytes:
    """AES-256-GCM. `aad` (connection id + org id) binds the ciphertext to its row, so it cannot be copied to another row or org."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return _VERSION + nonce + AESGCM(_key()).encrypt(nonce, plain.encode(), aad.encode())


def decrypt_credential(blob: bytes, aad: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if blob[:1] != _VERSION:
        raise ValueError("unknown credential format")
    return AESGCM(_key()).decrypt(blob[1:13], blob[13:], aad.encode()).decode()


def aad_for(conn: ProviderConnection) -> str:
    return f"{conn.id}:{conn.org_id}"


def hint_for(api_key: str) -> str:
    return "…" + api_key[-4:]


async def check_credential(provider: str, api_key: str) -> bool:
    """True if the provider accepts the key. Raises GatewayError when the provider cannot be reached at all."""
    if settings.MOCK_PROVIDER_CHECK and settings.ENV != "prod":
        return "bad" not in api_key
    url, headers = _CHECK[provider]
    try:
        async with httpx.AsyncClient(transport=TRANSPORT, timeout=15.0) as client:
            r = await client.get(url, headers=headers(api_key))
    except httpx.RequestError:
        raise GatewayError(502, "provider_unreachable", f"Could not reach {provider} to check the key. Try again in a moment.")
    if r.status_code in (401, 403):
        return False
    if r.status_code >= 500 or r.status_code == 429:
        raise GatewayError(502, "provider_unreachable", f"{provider} is not responding normally right now. Try again in a moment.")
    return r.status_code < 400


async def resolve_connection(session: AsyncSession, org_id: str, requested: str | None) -> ProviderConnection | None:
    """The org's own connection for this call: the requested provider's (default first), else the org default."""
    q = select(ProviderConnection).where(ProviderConnection.org_id == org_id).order_by(ProviderConnection.is_default.desc(), ProviderConnection.created_at)
    if requested:
        q = q.where(ProviderConnection.provider == requested.lower())
    else:
        q = q.where(ProviderConnection.is_default.is_(True))
    return (await session.execute(q.limit(1))).scalar_one_or_none()
