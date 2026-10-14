from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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


def _jwks_client():
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(settings.AUTH_JWKS_URL, cache_keys=True, lifespan=3600)
    return _jwks


def _verify_jwt(token: str) -> dict:
    """Verify a NEXORA account (Clerk) session token: RS256 signature via JWKS, issuer, expiry, and the page origin (azp)."""
    if not settings.AUTH_JWKS_URL or not settings.AUTH_ISSUER:
        raise GatewayError(500, "auth_not_configured", "Session verification is not configured.")
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], issuer=settings.AUTH_ISSUER,
                            leeway=5, options={"verify_aud": False, "require": ["exp", "iat", "sub", "iss"]})
    except jwt.PyJWTError:
        raise GatewayError(401, "invalid_session", "Your session is invalid or expired. Sign in again.")
    azp = claims.get("azp")
    if azp and azp not in settings.cors_list:  # token was minted for some other site
        raise GatewayError(401, "invalid_session", "Your session is invalid or expired. Sign in again.")
    return claims


def _org_and_role(claims: dict) -> tuple[str, str]:
    """Clerk session tokens v1 use org_id/org_role; v2 nests them in `o` (id, rol). No org = personal workspace."""
    o = claims.get("o") if isinstance(claims.get("o"), dict) else {}
    org = claims.get("org_id") or o.get("id") or claims["sub"]
    raw = claims.get("org_role") or ("org:" + o["rol"] if o.get("rol") else "")
    return org, {"org:admin": "admin"}.get(raw, "developer")


async def _get_or_create(session: AsyncSession, query, make):
    """First visits fire several requests at once, each trying to create the same row. The unique constraint decides the
    winner; the others roll back their savepoint and read the winner's row."""
    row = (await session.execute(query)).scalar_one_or_none()
    if row is not None:
        return row
    try:
        async with session.begin_nested():
            row = make()
            session.add(row)
    except IntegrityError:
        row = (await session.execute(query)).scalar_one()
    return row


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
        ext_org, role = _org_and_role(claims)
        ext_user, email = claims["sub"], claims.get("email", "")

    org = await _get_or_create(session, select(Organization).where(Organization.external_org_id == ext_org),
                               lambda: Organization(external_org_id=ext_org, name=ext_org, monthly_call_quota=settings.FREE_MONTHLY_QUOTA))
    first = (await session.execute(select(Member.id).where(Member.org_id == org.id).limit(1))).first() is None
    member = await _get_or_create(session, select(Member).where(Member.org_id == org.id, Member.external_user_id == ext_user),
                                  lambda: Member(org_id=org.id, external_user_id=ext_user, email=email, role="owner" if first else role))
    await session.commit()
    return Principal(org=org, member=member, role=member.role)


def require(min_role: str):
    async def dep(p: Principal = Depends(get_principal)) -> Principal:
        if ROLE_RANK[p.role] < ROLE_RANK[min_role]:
            raise GatewayError(403, "forbidden", f"This needs the {min_role} role or higher.")
        return p
    return dep
