"""Data access and portability (GDPR): everything Gateway stores about an organization, and about the caller."""
import datetime as dt
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from app.db import (ApiKey, Member, Organization, Policy, ProviderConnection, RequestLog, SecurityEvent, SessionLocal, Subscription, UsageDaily)
from app.deps import Principal, require
from app.errors import GatewayError
from app.ratelimit import limiter

router = APIRouter(prefix="/api")
log = logging.getLogger("gateway.export")
PAGE = 1000
NOTES = ("Everything Gateway stores about this organization. Prompt text is never stored (request logs hold a hash). "
         "API key secrets and provider API keys are not included: secrets are stored only as a hash or encrypted and are never readable. "
         "Request logs older than your plan's retention are replaced by daily counts in usage_daily. "
         "Billing records are held by Stripe.")
EXCLUDE = {"key_hash", "credential_enc"}


def _row(obj) -> dict:
    out = {}
    for col in obj.__table__.columns:
        if col.name in EXCLUDE:
            continue
        v = getattr(obj, col.name)
        out[col.name] = v.isoformat() if isinstance(v, (dt.datetime, dt.date)) else v
    return out


def _dump(v) -> str:
    return json.dumps(v, ensure_ascii=False)


async def _all(s, model, org_id):
    """Rows of one table for the org in pages of PAGE, ordered by id (stable), so memory stays flat for large orgs."""
    last = ""
    while True:
        rows = (await s.execute(select(model).where(model.org_id == org_id, model.id > last).order_by(model.id).limit(PAGE))).scalars().all()
        for r in rows:
            yield _row(r)
        if len(rows) < PAGE:
            return
        last = rows[-1].id


async def _export(org_id: str):
    async with SessionLocal() as s:
        org = await s.get(Organization, org_id)
        yield '{"generated_at": %s, "notes": %s, "organization": %s' % (_dump(dt.datetime.now(dt.timezone.utc).isoformat()), _dump(NOTES), _dump(_row(org)))
        for name, model in (("members", Member), ("api_keys", ApiKey), ("provider_connections", ProviderConnection),
                            ("policies", Policy), ("usage_daily", UsageDaily), ("security_events", SecurityEvent), ("request_logs", RequestLog)):
            yield f', "{name}": ['
            first = True
            async for row in _all(s, model, org_id):
                yield ("" if first else ",") + _dump(row)
                first = False
            yield "]"
        sub = await s.get(Subscription, org_id)
        yield ', "subscription": %s}' % _dump(_row(sub) if sub else None)


@router.get("/org/export")
async def export_org(p: Principal = Depends(require("admin"))):
    ok, retry = await limiter.allow(f"export:{p.org.id}", 3)  # a full export reads every table: keep it from being a load tool
    if not ok:
        raise GatewayError(429, "rate_limited", "Too many exports. Try again in a minute.", {"Retry-After": str(retry)})
    log.info("org export requested org=%s member=%s", p.org.id, p.member.id)  # an audit trail without personal data
    name = f"nexora-gateway-export-{p.org.id}-{dt.datetime.now(dt.timezone.utc).date()}.json"
    return StreamingResponse(_export(p.org.id), media_type="application/json",
                             headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.get("/me/export")
async def export_me(p: Principal = Depends(require("viewer", allow_suspended=True))):
    """The caller's own record: what Gateway holds about them as a person (not the organization's data or other members)."""
    return JSONResponse({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "member": _row(p.member),
                         "organization": {"id": p.org.id, "name": p.org.name},
                         "notes": "Gateway stores only your membership. Your account itself (name, sign-in) is held by the NEXORA account service."},
                        headers={"Cache-Control": "no-store"})
