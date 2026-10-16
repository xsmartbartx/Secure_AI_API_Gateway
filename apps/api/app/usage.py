"""Usage aggregation over live request logs plus the daily rollups that replace purged logs.
A UTC day lives in exactly one of the two places: the purge rolls a day up and deletes its logs in one transaction."""
import datetime as dt
from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import RequestLog, SessionLocal, UsageDaily, engine

Group = Literal["key", "model", "day"]
FIELDS = ("calls", "blocked", "errors", "tokens_in", "tokens_out")


def utc_midnight(d: dt.date) -> dt.datetime:
    return dt.datetime.combine(d, dt.time.min, dt.timezone.utc)


def log_day():
    """UTC calendar day of a log row. Postgres buckets timestamptz in the session time zone unless told otherwise."""
    if engine.dialect.name == "postgresql":
        return func.date(func.timezone("UTC", RequestLog.ts))
    return func.date(RequestLog.ts)


async def usage_rows(s: AsyncSession, org_id: str, start: dt.date, end: dt.date, group: Group) -> dict[str | None, dict]:
    """Totals per dimension value (key id / model / 'YYYY-MM-DD') for start..end inclusive, from logs and rollups."""
    lo, hi = utc_midnight(start), utc_midnight(end + dt.timedelta(days=1))
    ldim = {"key": RequestLog.key_id, "model": func.coalesce(RequestLog.model, "unknown"), "day": log_day()}[group]
    logs = (select(ldim.label("dim"), func.count().label("calls"),
                   func.sum(case((RequestLog.decision == "block", 1), else_=0)).label("blocked"),
                   func.sum(case((RequestLog.decision == "error", 1), else_=0)).label("errors"),
                   func.sum(RequestLog.tokens_in).label("tin"), func.sum(RequestLog.tokens_out).label("tout"))
            .where(RequestLog.org_id == org_id, RequestLog.ts >= lo, RequestLog.ts < hi)
            .group_by("dim"))  # by label: a bind-parameter expression repeated in GROUP BY is rejected by Postgres
    rdim = {"key": UsageDaily.key_id, "model": UsageDaily.model, "day": UsageDaily.day}[group]
    rolled = (select(rdim.label("dim"), func.sum(UsageDaily.calls), func.sum(UsageDaily.blocked), func.sum(UsageDaily.errors),
                     func.sum(UsageDaily.tokens_in), func.sum(UsageDaily.tokens_out))
              .where(UsageDaily.org_id == org_id, UsageDaily.day >= start, UsageDaily.day <= end)
              .group_by("dim"))
    out: dict[str | None, dict] = {}
    for dim, *vals in list((await s.execute(logs)).all()) + list((await s.execute(rolled)).all()):
        key = str(dim) if group == "day" else dim
        row = out.setdefault(key, dict.fromkeys(FIELDS, 0))
        for f, v in zip(FIELDS, vals):
            row[f] += int(v or 0)
    return out


async def billable_this_month(org_id: str, now: dt.datetime | None = None, s: AsyncSession | None = None) -> int:
    """Calls that count toward the monthly quota: live logs (not errors) plus billable calls already rolled up."""
    now = now or dt.datetime.now(dt.timezone.utc)
    first = now.date().replace(day=1)

    async def run(sess: AsyncSession) -> int:
        live = (await sess.execute(select(func.count()).select_from(RequestLog).where(
            RequestLog.org_id == org_id, RequestLog.ts >= utc_midnight(first), RequestLog.decision.notin_(("error", "block"))))).scalar_one()
        rolled = (await sess.execute(select(func.coalesce(func.sum(UsageDaily.billable), 0)).where(
            UsageDaily.org_id == org_id, UsageDaily.day >= first))).scalar_one()
        return int(live) + int(rolled)

    if s is not None:
        return await run(s)
    async with SessionLocal() as own:
        return await run(own)
