import datetime as dt

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import ApiKey, RequestLog, SecurityEvent, get_session
from app.deps import Principal, month_start, require
from app.errors import GatewayError
from app.keys import generate_key

router = APIRouter(prefix="/api")


def _key_out(k: ApiKey) -> dict:
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "last4": k.last4, "rpm_limit": k.rpm_limit,
            "created_at": k.created_at, "last_used_at": k.last_used_at, "revoked_at": k.revoked_at}


class KeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    rpm_limit: int = Field(60, ge=1, le=10_000)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


@router.get("/me")
async def me(p: Principal = Depends(require("viewer"))):
    return {"org": {"id": p.org.id, "name": p.org.name, "plan": p.org.plan, "quota": p.org.monthly_call_quota},
            "member": {"email": p.member.email, "role": p.role}}


@router.get("/keys")
async def list_keys(p: Principal = Depends(require("viewer")), s: AsyncSession = Depends(get_session)):
    rows = (await s.execute(select(ApiKey).where(ApiKey.org_id == p.org.id).order_by(ApiKey.created_at.desc()))).scalars().all()
    return {"items": [_key_out(k) for k in rows]}


@router.post("/keys", status_code=201)
async def create_key(body: KeyCreate, p: Principal = Depends(require("developer")), s: AsyncSession = Depends(get_session)):
    secret, prefix, h, last4 = generate_key()
    k = ApiKey(org_id=p.org.id, name=body.name, prefix=prefix, key_hash=h, last4=last4, rpm_limit=body.rpm_limit)
    s.add(k)
    await s.commit()
    return {**_key_out(k), "secret": secret}  # the only time the secret is returned


@router.post("/keys/{key_id}/revoke")
async def revoke_key(key_id: str, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    k = await s.get(ApiKey, key_id)
    if k is None or k.org_id != p.org.id:
        raise GatewayError(404, "not_found", "Key not found.")
    k.revoked_at = k.revoked_at or dt.datetime.now(dt.timezone.utc)
    await s.commit()
    return _key_out(k)


@router.post("/keys/{key_id}/rotate", status_code=201)
async def rotate_key(key_id: str, p: Principal = Depends(require("admin")), s: AsyncSession = Depends(get_session)):
    old = await s.get(ApiKey, key_id)
    if old is None or old.org_id != p.org.id:
        raise GatewayError(404, "not_found", "Key not found.")
    secret, prefix, h, last4 = generate_key()
    new = ApiKey(org_id=p.org.id, name=old.name, prefix=prefix, key_hash=h, last4=last4, rpm_limit=old.rpm_limit)
    s.add(new)
    await s.commit()
    return {**_key_out(new), "secret": secret, "replaces": old.id}  # old key stays active until revoked


def _log_out(l: RequestLog) -> dict:
    return {"id": l.id, "request_id": l.request_id, "ts": l.ts, "key_id": l.key_id, "provider": l.provider,
            "model": l.model, "status_code": l.status_code, "decision": l.decision, "risk_score": l.risk_score,
            "tokens_in": l.tokens_in, "tokens_out": l.tokens_out, "latency_ms": l.latency_ms}


@router.get("/logs")
async def list_logs(decision: str | None = None, limit: int = Query(50, ge=1, le=200), before: dt.datetime | None = None,
                    p: Principal = Depends(require("viewer")), s: AsyncSession = Depends(get_session)):
    q = select(RequestLog).where(RequestLog.org_id == p.org.id)
    if decision:
        q = q.where(RequestLog.decision == decision)
    if before:
        q = q.where(RequestLog.ts < before)
    rows = (await s.execute(q.order_by(RequestLog.ts.desc()).limit(limit + 1))).scalars().all()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [_log_out(r) for r in rows], "next_before": rows[-1].ts if more and rows else None}


@router.get("/logs/{log_id}")
async def get_log(log_id: str, p: Principal = Depends(require("viewer")), s: AsyncSession = Depends(get_session)):
    l = await s.get(RequestLog, log_id)
    if l is None or l.org_id != p.org.id:
        raise GatewayError(404, "not_found", "Log entry not found.")
    return {**_log_out(l), "prompt_hash": l.prompt_hash}


@router.get("/overview")
async def overview(days: int = Query(7, ge=1, le=90), p: Principal = Depends(require("viewer")),
                   s: AsyncSession = Depends(get_session)):
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    rows = (await s.execute(select(RequestLog).where(RequestLog.org_id == p.org.id, RequestLog.ts >= since))).scalars().all()
    by_day: dict[str, dict] = {}
    for r in rows:
        d = r.ts.date().isoformat()
        b = by_day.setdefault(d, {"day": d, "calls": 0, "blocked": 0, "errors": 0})
        b["calls"] += 1
        b["blocked"] += r.decision == "block"
        b["errors"] += r.decision == "error"
    month_calls = (await s.execute(select(func.count()).select_from(RequestLog).where(
        RequestLog.org_id == p.org.id, RequestLog.ts >= month_start(), RequestLog.decision != "error"))).scalar_one()
    lat = sorted(r.latency_ms for r in rows if r.latency_ms is not None)
    return {
        "calls": len(rows), "blocked": sum(r.decision == "block" for r in rows),
        "errors": sum(r.decision == "error" for r in rows),
        "tokens": sum(r.tokens_in + r.tokens_out for r in rows),
        "p50_latency_ms": lat[len(lat) // 2] if lat else None,
        "quota": {"used": month_calls, "limit": p.org.monthly_call_quota},
        "series": sorted(by_day.values(), key=lambda x: x["day"]),
    }


@router.get("/usage")
async def usage(days: int = Query(30, ge=1, le=90), p: Principal = Depends(require("viewer")),
                s: AsyncSession = Depends(get_session)):
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    rows = (await s.execute(select(RequestLog).where(RequestLog.org_id == p.org.id, RequestLog.ts >= since))).scalars().all()
    by_model: dict[str, dict] = {}
    for r in rows:
        m = by_model.setdefault(r.model or "unknown", {"model": r.model or "unknown", "calls": 0, "tokens_in": 0, "tokens_out": 0})
        m["calls"] += 1
        m["tokens_in"] += r.tokens_in
        m["tokens_out"] += r.tokens_out
    return {"by_model": sorted(by_model.values(), key=lambda x: -x["calls"])}


@router.get("/security-events")
async def security_events(p: Principal = Depends(require("viewer")), s: AsyncSession = Depends(get_session)):
    rows = (await s.execute(select(SecurityEvent).where(SecurityEvent.org_id == p.org.id)
                            .order_by(SecurityEvent.ts.desc()).limit(100))).scalars().all()
    return {"items": [{"id": e.id, "type": e.type, "severity": e.severity, "rule_id": e.rule_id, "ts": e.ts,
                       "log_id": e.log_id} for e in rows]}


class PlaygroundBody(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=20_000)
    system: str | None = Field(None, max_length=20_000)
    model: str | None = None


@router.post("/playground")
async def playground(body: PlaygroundBody, request: Request, p: Principal = Depends(require("developer")),
                     s: AsyncSession = Depends(get_session)):
    """Runs a call as the signed-in user; uses the same pipeline as /v1/chat but needs no key. Counts toward quota."""
    from app.routers.data import _chat
    from app.schemas import ChatMessage, UnifiedChatRequest

    msgs = ([ChatMessage(role="system", content=body.system)] if body.system else []) + [ChatMessage(role="user", content=body.prompt)]
    pseudo = ApiKey(id="playground:" + p.member.id, org_id=p.org.id, name="playground", prefix="", key_hash=b"", last4="", rpm_limit=30)
    return await _chat(request, UnifiedChatRequest(messages=msgs, model=body.model), pseudo, s, track_key=False)
