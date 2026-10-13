import datetime as dt
from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import ApiKey, Member, Organization, get_session
from app.errors import GatewayError
from app.keys import PREFIX, hash_key

ROLE_RANK = {"viewer": 0, "developer": 1, "admin": 2, "owner": 3}


@dataclass
class Principal:
    org: Organization
    member: Member
    role: str


async def get_api_key(request: Request, session: AsyncSession = Depends(get_session)) -> ApiKey:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise GatewayError(401, "missing_key", "Send your API key as 'Authorization: Bearer nx_live_...'.")
    secret = header.split(" ", 1)[1].strip()
    if not secret.startswith(PREFIX):
        raise GatewayError(401, "invalid_key", "That API key is not valid.")
    key = (await session.execute(select(ApiKey).where(ApiKey.key_hash == hash_key(secret)))).scalar_one_or_none()
    if key is None or key.revoked_at is not None:
        raise GatewayError(401, "invalid_key", "That API key is not valid or has been revoked.")
    return key


_jwks = None


def _verify_jwt(token: str) -> dict:
    global _jwks
    if not settings.AUTH_JWKS_URL:
        raise GatewayError(500, "auth_not_configured", "Session verification is not configured.")
    _jwks = _jwks or jwt.PyJWKClient(settings.AUTH_JWKS_URL)
    try:
        signing_key = _jwks.get_signing_key_from_jwt(token)
        return jwt.decode(token, signing_key.key, algorithms=["RS256"], issuer=settings.AUTH_ISSUER or None,
                          options={"verify_aud": False})
    except jwt.PyJWTError:
        raise GatewayError(401, "invalid_session", "Your session is invalid or expired. Sign in again.")


async def get_principal(request: Request, session: AsyncSession = Depends(get_session)) -> Principal:
    if settings.ENV != "prod" and settings.DEV_AUTH and request.headers.get("x-dev-org"):
        ext_org = request.headers["x-dev-org"]
        ext_user = request.headers.get("x-dev-user", "dev-user")
        role = request.headers.get("x-dev-role", "owner")
        email = f"{ext_user}@dev.local"
    else:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            raise GatewayError(401, "missing_session", "Sign in to continue.")
        claims = _verify_jwt(header.split(" ", 1)[1])
        ext_org = claims.get("org_id") or claims.get("sub")
        ext_user, email = claims["sub"], claims.get("email", "")
        role = {"org:admin": "admin"}.get(claims.get("org_role", ""), "developer")

    org = (await session.execute(select(Organization).where(Organization.external_org_id == ext_org))).scalar_one_or_none()
    if org is None:  # first visit: provision from the account org
        org = Organization(external_org_id=ext_org, name=ext_org, monthly_call_quota=settings.FREE_MONTHLY_QUOTA)
        session.add(org)
        await session.flush()
    member = (await session.execute(select(Member).where(Member.org_id == org.id, Member.external_user_id == ext_user))).scalar_one_or_none()
    if member is None:
        first = (await session.execute(select(Member).where(Member.org_id == org.id).limit(1))).scalar_one_or_none() is None
        member = Member(org_id=org.id, external_user_id=ext_user, email=email, role="owner" if first else role)
        session.add(member)
    await session.commit()
    return Principal(org=org, member=member, role=member.role)


def require(min_role: str):
    async def dep(p: Principal = Depends(get_principal)) -> Principal:
        if ROLE_RANK[p.role] < ROLE_RANK[min_role]:
            raise GatewayError(403, "forbidden", f"This needs the {min_role} role or higher.")
        return p
    return dep


def month_start() -> dt.datetime:
    n = dt.datetime.now(dt.timezone.utc)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
