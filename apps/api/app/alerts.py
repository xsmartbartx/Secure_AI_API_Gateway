"""Email alerts when an organization nears or reaches its monthly call quota. Best effort: the dashboard banner is the reliable channel."""
import asyncio
import datetime as dt
import logging

import httpx
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import AlertSent, Member, Organization, SessionLocal
from app.ratelimit import limiter

log = logging.getLogger("gateway.alerts")
TRANSPORT = None  # tests inject an httpx transport
THRESHOLDS = ((80, "quota_80"), (100, "quota_100"))
_background: set[asyncio.Task] = set()


def schedule(coro) -> None:
    """Run an alert in the background without delaying the call that triggered it (and keep a reference so it is not collected)."""
    task = asyncio.ensure_future(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _recipients(org_id: str) -> list[str]:
    async with SessionLocal() as s:
        rows = (await s.execute(select(Member.email).where(Member.org_id == org_id, Member.role.in_(("owner", "admin")), Member.status == "active"))).scalars().all()
    return sorted({e for e in rows if e and "@" in e})


async def _send(to: list[str], subject: str, text: str) -> None:
    async with httpx.AsyncClient(transport=TRANSPORT, timeout=10.0) as client:
        r = await client.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                              json={"from": settings.ALERT_FROM_EMAIL, "to": to, "subject": subject, "text": text})
        r.raise_for_status()


async def maybe_alert(org_id: str, used: int, limit: int) -> None:
    """Send the 80% and 100% alerts once per organization per month. Never raises."""
    try:
        if limit <= 0 or not settings.RESEND_API_KEY or not settings.ALERT_FROM_EMAIL:
            return
        month = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")
        for pct, kind in THRESHOLDS:
            if used * 100 >= pct * limit:
                await _alert(org_id, month, kind, pct, used, limit)
    except Exception:
        log.exception("quota alert failed for org %s", org_id)


async def _alert(org_id: str, month: str, kind: str, pct: int, used: int, limit: int) -> None:
    to = await _recipients(org_id)
    if not to:
        return
    async with SessionLocal() as s:
        if (await s.execute(select(AlertSent.id).where(AlertSent.org_id == org_id, AlertSent.month == month, AlertSent.kind == kind))).first():
            return
        org = await s.get(Organization, org_id)
        s.add(AlertSent(org_id=org_id, month=month, kind=kind))
        try:
            await s.commit()  # claim first: if two calls cross the threshold together, only one gets past this point
        except IntegrityError:
            return
    ok, _ = await limiter.allow(f"alert:{org_id}:{kind}", 1, fail_open=False)  # at most one delivery attempt a minute, even while the provider or Redis is down
    reached = pct >= 100
    subject = f"NEXORA Gateway: you've used {pct}% of this month's calls" + (" (limit reached)" if reached else "")
    text = (f"Your organization \"{org.name}\" has used {used} of {limit} calls this month on the {org.plan} plan.\n\n"
            + ("Further calls are rejected until the month resets (UTC) or you upgrade.\n\n" if reached else "At the limit, further calls are rejected until the month resets (UTC) or you upgrade.\n\n")
            + f"Billing and plans: {settings.APP_URL}/app/billing\n")
    try:
        if not ok:
            raise RuntimeError("alert delivery rate limited")
        await _send(to, subject, text)
    except Exception:
        log.exception("could not send the %s alert for org %s", kind, org_id)
        async with SessionLocal() as s:  # release the claim so a later call can retry
            await s.execute(delete(AlertSent).where(AlertSent.org_id == org_id, AlertSent.month == month, AlertSent.kind == kind))
            await s.commit()
