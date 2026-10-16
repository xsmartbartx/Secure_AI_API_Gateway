"""Log retention. Prompt text is never stored; request logs hold metadata only. Logs older than the plan's retention
are rolled up into usage_daily (counts only) and deleted, so usage history and the monthly quota keep working."""
import asyncio
import datetime as dt
import logging

from sqlalchemy import case, delete, func, select, update

from app.config import settings
from app.db import Organization, RequestLog, SecurityEvent, SessionLocal, UsageDaily
from app.usage import log_day, utc_midnight

log = logging.getLogger("gateway.retention")

RETENTION_DAYS = {"free": 7, "starter": 30, "team": 90, "enterprise": 365}


async def purge_org(org_id: str, plan: str, now: dt.datetime) -> int:
    """Roll up and delete whole UTC days older than the plan's retention. One transaction per day, so a day is never
    in both places (the rollup is merged into any existing one). Logs from the day `retention` days ago are kept: effective retention is the full window plus up to 24h."""
    cutoff = utc_midnight((now - dt.timedelta(days=RETENTION_DAYS.get(plan, 7))).date())
    deleted = 0
    async with SessionLocal() as s:
        days = [d for (d,) in (await s.execute(select(log_day()).where(RequestLog.org_id == org_id, RequestLog.ts < cutoff).distinct())).all()]
    for d in sorted(str(x) for x in days):
        day = dt.date.fromisoformat(d)
        lo, hi = utc_midnight(day), utc_midnight(day + dt.timedelta(days=1))
        async with SessionLocal() as s, s.begin():
            where = (RequestLog.org_id == org_id, RequestLog.ts >= lo, RequestLog.ts < hi)
            model = func.coalesce(RequestLog.model, "unknown")
            agg = (await s.execute(
                select(RequestLog.key_id, model, func.count(),
                       func.sum(case((RequestLog.decision.notin_(("error", "block")), 1), else_=0)),
                       func.sum(case((RequestLog.decision == "block", 1), else_=0)),
                       func.sum(case((RequestLog.decision == "error", 1), else_=0)),
                       func.sum(RequestLog.tokens_in), func.sum(RequestLog.tokens_out))
                .where(*where).group_by(RequestLog.key_id, model))).all()
            existing = {(u.key_id, u.model): u for u in (await s.execute(
                select(UsageDaily).where(UsageDaily.org_id == org_id, UsageDaily.day == day))).scalars()}
            for key_id, mdl, calls, billable, blocked, errors, tin, tout in agg:
                # merge, never replace: a straggler log for an already rolled-up day must add to it, not erase it
                u = existing.get((key_id, mdl))
                if u is None:
                    u = UsageDaily(org_id=org_id, day=day, key_id=key_id, model=mdl, calls=0, billable=0, blocked=0, errors=0, tokens_in=0, tokens_out=0)
                    s.add(u)
                u.calls += calls; u.billable += int(billable or 0); u.blocked += int(blocked or 0); u.errors += int(errors or 0)
                u.tokens_in += int(tin or 0); u.tokens_out += int(tout or 0)
            await s.execute(delete(SecurityEvent).where(SecurityEvent.log_id.in_(select(RequestLog.id).where(*where))))
            deleted += (await s.execute(delete(RequestLog).where(*where))).rowcount
    return deleted


STALE_PENDING_MINUTES = 15


async def settle_stale_pending(now: dt.datetime) -> int:
    """A call is reserved as 'pending' before it is sent upstream. If the process died mid-call the row never settles; after a
    grace period (longer than any call) mark it as an error so it stops counting toward the quota and shows honestly in the logs."""
    async with SessionLocal() as s, s.begin():
        res = await s.execute(update(RequestLog).where(RequestLog.decision == "pending", RequestLog.ts < now - dt.timedelta(minutes=STALE_PENDING_MINUTES))
                              .values(decision="error", status_code=500))
        return res.rowcount


async def purge_expired(now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    stale = await settle_stale_pending(now)
    async with SessionLocal() as s:
        orgs = [(o.id, o.plan) for o in (await s.execute(select(Organization))).scalars()]
    total = 0
    for org_id, plan in orgs:
        try:
            total += await purge_org(org_id, plan, now)
        except Exception:  # one bad org must not stop the others
            log.exception("retention purge failed for org %s", org_id)
    log.info("retention purge deleted %d log rows across %d orgs", total, len(orgs))
    return {"orgs": len(orgs), "logs_deleted": total, "stale_settled": stale}


async def retention_loop() -> None:
    """In-process scheduler. Safe with several workers: the purge is idempotent. Prod can also run `python -m app.retention`."""
    await asyncio.sleep(60)
    while True:
        try:
            await purge_expired()
        except Exception:
            log.exception("retention loop iteration failed")
        await asyncio.sleep(settings.RETENTION_INTERVAL_HOURS * 3600)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(purge_expired()))
