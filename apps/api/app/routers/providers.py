from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import providers
from app.db import ProviderConnection, get_session
from app.deps import Principal, require
from app.errors import GatewayError
from app.ratelimit import limiter

router = APIRouter(prefix="/api/providers")
MAX_CONNECTIONS = 10


def _out(c: ProviderConnection) -> dict:
    return {"id": c.id, "provider": c.provider, "label": c.label, "hint": c.hint, "is_default": c.is_default,
            "status": c.status, "created_at": c.created_at}  # the key itself is never part of any response


class ConnectionIn(BaseModel):
    provider: Literal["anthropic", "openai"]
    label: str = Field(..., min_length=1, max_length=60)
    api_key: str = Field(..., min_length=12, max_length=400)

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("label must not be blank")
        return v

    @field_validator("api_key")
    @classmethod
    def _key(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 12 or any(ch.isspace() for ch in v):
            raise ValueError("api_key looks malformed")
        return v


async def _owned(s: AsyncSession, p: Principal, conn_id: str) -> ProviderConnection:
    c = await s.get(ProviderConnection, conn_id)
    if c is None or c.org_id != p.org.id:
        raise GatewayError(404, "not_found", "Provider connection not found.")
    return c


@router.get("")
async def list_connections(p: Principal = Depends(require("developer")), s: AsyncSession = Depends(get_session)):
    rows = (await s.execute(select(ProviderConnection).where(ProviderConnection.org_id == p.org.id)
                            .order_by(ProviderConnection.is_default.desc(), ProviderConnection.created_at))).scalars().all()
    return {"items": [_out(c) for c in rows]}


async def _count(s: AsyncSession, org_id: str) -> int:
    return (await s.execute(select(func.count()).select_from(ProviderConnection).where(ProviderConnection.org_id == org_id))).scalar_one()


@router.post("", status_code=201)
async def add_connection(body: ConnectionIn, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    if await _count(s, p.org.id) >= MAX_CONNECTIONS:  # early exit; re-checked below because the provider call takes a while
        raise GatewayError(409, "too_many_connections", f"You can store at most {MAX_CONNECTIONS} provider keys.")
    ok, retry = await limiter.allow(f"verify:{p.org.id}", 10)  # each save/test makes an outbound request
    if not ok:
        raise GatewayError(429, "rate_limited", "Too many key checks. Wait a minute.", {"Retry-After": str(retry)})
    if not await providers.check_credential(body.provider, body.api_key):  # never store a key the provider refuses
        raise GatewayError(422, "provider_rejected_key", f"{body.provider} rejected that API key. Check it and try again.")

    # Everything read before the provider call may be stale by now. Insert first and let the database arbitrate: the
    # partial unique index allows one default per org, so a concurrent first add that loses falls back to "not default".
    def make(is_default: bool) -> ProviderConnection:
        return ProviderConnection(org_id=p.org.id, provider=body.provider, label=body.label, hint=providers.hint_for(body.api_key),
                                  credential_enc=b"", is_default=is_default, status="ok")
    c = make(await _count(s, p.org.id) == 0)
    try:
        async with s.begin_nested():
            s.add(c)
            await s.flush()
    except IntegrityError:
        c = make(False)
        s.add(c)
        await s.flush()
    if await _count(s, p.org.id) > MAX_CONNECTIONS:  # concurrent adds all passed the early check: the excess back out
        await s.delete(c)
        await s.commit()
        raise GatewayError(409, "too_many_connections", f"You can store at most {MAX_CONNECTIONS} provider keys.")
    c.credential_enc = providers.encrypt_credential(body.api_key, providers.aad_for(c))  # the id is part of the encryption context
    await s.commit()
    return _out(c)


@router.post("/{conn_id}/test")
async def test_connection(conn_id: str, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    c = await _owned(s, p, conn_id)
    ok, retry = await limiter.allow(f"verify:{p.org.id}", 10)
    if not ok:
        raise GatewayError(429, "rate_limited", "Too many key checks. Wait a minute.", {"Retry-After": str(retry)})
    key = providers.decrypt_credential(c.credential_enc, providers.aad_for(c))
    c.status = "ok" if await providers.check_credential(c.provider, key) else "failing"
    await s.commit()
    return _out(c)


@router.post("/{conn_id}/default")
async def make_default(conn_id: str, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    c = await _owned(s, p, conn_id)
    await s.execute(update(ProviderConnection).where(ProviderConnection.org_id == p.org.id).values(is_default=False))
    c.is_default = True
    await s.commit()
    return _out(c)


@router.delete("/{conn_id}")
async def remove_connection(conn_id: str, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    c = await _owned(s, p, conn_id)
    await s.delete(c)
    await s.commit()
    return {"deleted": True}
