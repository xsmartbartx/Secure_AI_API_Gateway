import csv
import datetime as dt
import io
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import accounts
from app.retention import RETENTION_DAYS
from app.db import Member, ApiKey, RequestLog, SecurityEvent, get_session
from app.deps import Principal, require
from app.usage import billable_this_month, usage_rows, utc_midnight
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
async def me(p: Principal = Depends(require("viewer", allow_suspended=True))):
    return {"org": {"id": p.org.id, "name": p.org.name, "plan": p.org.plan, "quota": p.org.monthly_call_quota,
                    "retention_days": RETENTION_DAYS.get(p.org.plan, 7)},
            "member": {"email": p.member.email, "role": p.role, "status": p.member.status}}


class OrgDelete(BaseModel):
    confirm: str = ""


@router.post("/org/delete")
async def delete_org(body: OrgDelete, p: Principal = Depends(require("owner")), s: AsyncSession = Depends(get_session)):
    """Permanently delete the organization and everything stored for it. The caller must type the organization's name."""
    if body.confirm != p.org.name:
        raise GatewayError(422, "confirmation_mismatch", "Type the organization name exactly to confirm.")
    await accounts.cancel_billing(s, p.org.id, strict=True)
    await accounts.delete_org_data(s, p.org.id)
    await s.commit()
    return {"deleted": True}


@router.delete("/me")
async def leave_org(p: Principal = Depends(require("viewer", allow_suspended=True)), s: AsyncSession = Depends(get_session)):
    """Remove the caller's membership (their email and account id) from this organization."""
    others = (await s.execute(select(Member).where(Member.org_id == p.org.id, Member.id != p.member.id))).scalars().all()
    if not others:
        raise GatewayError(409, "last_member", "You are the only member. Delete the organization instead.")
    if p.role == "owner" and not any(m.role == "owner" for m in others):
        raise GatewayError(409, "last_owner", "Make another member an owner first, or delete the organization.")
    await s.delete(p.member)
    await s.commit()
    return {"left": True}


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
    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=days - 1)  # `days` UTC calendar days including today
    by_day = await usage_rows(s, p.org.id, start, today, "day")
    series = [{"day": d, "calls": v["calls"], "blocked": v["blocked"], "errors": v["errors"]} for d, v in sorted(by_day.items())]
    lat = sorted(x for (x,) in (await s.execute(select(RequestLog.latency_ms).where(
        RequestLog.org_id == p.org.id, RequestLog.ts >= utc_midnight(start), RequestLog.latency_ms.is_not(None)))).all())
    return {
        "calls": sum(v["calls"] for v in by_day.values()), "blocked": sum(v["blocked"] for v in by_day.values()),
        "errors": sum(v["errors"] for v in by_day.values()),
        "tokens": sum(v["tokens_in"] + v["tokens_out"] for v in by_day.values()),
        "p50_latency_ms": lat[len(lat) // 2] if lat else None,  # latency is only kept with the logs (retention window)
        "quota": {"used": await billable_this_month(p.org.id, s=s), "limit": p.org.monthly_call_quota},
        "series": series,
    }


def _csv_cell(v) -> str:
    """Spreadsheet formula injection: a key or model name like =HYPERLINK(...) must not run when the CSV is opened."""
    v = str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


@router.get("/usage")
async def usage(from_: dt.date | None = Query(None, alias="from"), to: dt.date | None = None,
                group: Literal["key", "model", "day"] = "key", format: Literal["json", "csv"] = "json",
                p: Principal = Depends(require("viewer")), s: AsyncSession = Depends(get_session)):
    """Usage between two UTC dates (inclusive), grouped by key, model or day. Default: the last 30 days."""
    to = to or dt.datetime.now(dt.timezone.utc).date()
    from_ = from_ or to - dt.timedelta(days=29)
    if from_ > to:
        raise GatewayError(422, "invalid_range", "'from' must not be after 'to'.")
    if (to - from_).days > 366:
        raise GatewayError(422, "invalid_range", "The range can be at most 366 days.")
    agg = await usage_rows(s, p.org.id, from_, to, group)

    keys = {}
    if group == "key":
        keys = {k.id: k for k in (await s.execute(select(ApiKey).where(ApiKey.org_id == p.org.id))).scalars()}
    rows = []
    for dim, v in agg.items():
        row = {"id": dim if group == "key" else None, "label": str(dim), **v}
        if group == "key":
            k = keys.get(dim)
            row["label"] = k.name if k else ("Playground" if dim is None else "Deleted key")
            row["prefix"] = f"{k.prefix}…{k.last4}" if k else None
            row["revoked"] = bool(k and k.revoked_at)
        rows.append(row)
    rows.sort(key=(lambda x: x["label"]) if group == "day" else (lambda x: -x["calls"]))
    totals = {f: sum(r[f] for r in rows) for f in ("calls", "blocked", "errors", "tokens_in", "tokens_out")}

    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["label", "calls", "blocked", "errors", "tokens_in", "tokens_out"])
        for r in rows:
            w.writerow([_csv_cell(r["label"]), r["calls"], r["blocked"], r["errors"], r["tokens_in"], r["tokens_out"]])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="usage-{group}-{from_}-{to}.csv"'})
    return {"from": from_.isoformat(), "to": to.isoformat(), "group": group, "rows": rows, "totals": totals}


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
    stream: bool = False


@router.post("/playground")
async def playground(body: PlaygroundBody, request: Request, p: Principal = Depends(require("developer")),
                     s: AsyncSession = Depends(get_session)):
    """Runs a call as the signed-in user; uses the same pipeline as /v1/chat but needs no key. Counts toward quota."""
    from app.routers.data import _chat, _chat_stream
    from app.schemas import ChatMessage, UnifiedChatRequest

    msgs = ([ChatMessage(role="system", content=body.system)] if body.system else []) + [ChatMessage(role="user", content=body.prompt)]
    pseudo = ApiKey(id="playground:" + p.member.id, org_id=p.org.id, name="playground", prefix="", key_hash=b"", last4="", rpm_limit=30)
    req = UnifiedChatRequest(messages=msgs, model=body.model, stream=body.stream)
    if body.stream:
        return await _chat_stream(request, req, pseudo, s, track_key=False)
    return await _chat(request, req, pseudo, s, track_key=False)
