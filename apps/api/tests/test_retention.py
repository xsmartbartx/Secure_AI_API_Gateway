import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import datetime as dt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db import ApiKey, Base, Organization, RequestLog, SecurityEvent, SessionLocal, UsageDaily, engine
from app.main import app
from app.retention import RETENTION_DAYS, purge_expired
from app.usage import billable_this_month

A = {"x-dev-org": "org_r", "x-dev-user": "r"}
NOW = dt.datetime(2026, 10, 20, 15, 30, tzinfo=dt.timezone.utc)


@pytest.fixture(autouse=True)
async def fresh():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def org_and_key(client, headers=A):
    k = (await client.post("/api/keys", json={"name": "k"}, headers=headers)).json()
    org = (await client.get("/api/me", headers=headers)).json()["org"]["id"]
    return org, k["id"]


async def log(org, key, ts, model="m1", decision="allow", tin=10, tout=20, event=False):
    async with SessionLocal() as s:
        l = RequestLog(org_id=org, key_id=key, request_id="r", ts=ts, provider="mock", model=model,
                       status_code=200, decision=decision, tokens_in=tin, tokens_out=tout)
        s.add(l)
        await s.flush()
        if event:
            s.add(SecurityEvent(org_id=org, log_id=l.id, type="prompt_injection", severity="high"))
        await s.commit()


async def count(model, org):
    async with SessionLocal() as s:
        return (await s.execute(select(func.count()).select_from(model).where(model.org_id == org))).scalar_one()


def days_ago(n, hour=12):
    return (NOW - dt.timedelta(days=n)).replace(hour=hour, minute=0)


async def test_retention_table():
    assert RETENTION_DAYS["free"] == 7 and RETENTION_DAYS["starter"] == 30


async def test_purges_only_expired_logs_for_the_plan(client):
    org, key = await org_and_key(client)
    await log(org, key, days_ago(2))      # kept
    await log(org, key, days_ago(7))      # day (now-7d) is still inside retention
    await log(org, key, days_ago(8), event=True)
    await log(org, key, days_ago(20))
    res = await purge_expired(NOW)
    assert res["logs_deleted"] == 2 and await count(RequestLog, org) == 2
    assert await count(SecurityEvent, org) == 0  # events of purged logs go with them


async def test_starter_keeps_30_days(client):
    org, key = await org_and_key(client)
    async with SessionLocal() as s:
        o = await s.get(Organization, org); o.plan = "starter"; await s.commit()
    await log(org, key, days_ago(20)); await log(org, key, days_ago(45))
    await purge_expired(NOW)
    assert await count(RequestLog, org) == 1


async def test_purge_is_idempotent_and_keeps_other_orgs(client):
    org, key = await org_and_key(client)
    other, okey = await org_and_key(client, {"x-dev-org": "org_x", "x-dev-user": "x"})
    await log(org, key, days_ago(30)); await log(other, okey, days_ago(1))
    assert (await purge_expired(NOW))["logs_deleted"] == 1
    assert (await purge_expired(NOW))["logs_deleted"] == 0
    assert await count(RequestLog, other) == 1


async def test_rollup_preserves_usage_numbers(client, monkeypatch):
    org, key = await org_and_key(client)
    for _ in range(3): await log(org, key, days_ago(10, 9))
    await log(org, key, days_ago(10, 20), model="m2", decision="error", tin=0, tout=0)
    await log(org, None, days_ago(10, 20), decision="block")
    await log(org, key, days_ago(1))
    start, end = days_ago(12).date().isoformat(), NOW.date().isoformat()

    before = {g: (await client.get(f"/api/usage?from={start}&to={end}&group={g}", headers=A)).json() for g in ("key", "model", "day")}
    await purge_expired(NOW)
    assert await count(RequestLog, org) == 1 and await count(UsageDaily, org) > 0
    after = {g: (await client.get(f"/api/usage?from={start}&to={end}&group={g}", headers=A)).json() for g in ("key", "model", "day")}
    for g in before:
        assert after[g]["totals"] == before[g]["totals"], g
        assert sorted((r["label"], r["calls"]) for r in after[g]["rows"]) == sorted((r["label"], r["calls"]) for r in before[g]["rows"]), g


async def test_rollup_is_not_double_counted_on_rerun(client):
    org, key = await org_and_key(client)
    await log(org, key, days_ago(10))
    await purge_expired(NOW)
    first = await count(UsageDaily, org)
    await log(org, key, days_ago(10, 13))  # a straggler for an already rolled-up day
    await purge_expired(NOW)
    async with SessionLocal() as s:
        total = (await s.execute(select(func.sum(UsageDaily.calls)).where(UsageDaily.org_id == org))).scalar_one()
    assert first == 1 and total == 2  # replaced the day's rollup with the full recount, not added twice


async def test_monthly_quota_survives_purge(client):
    org, key = await org_and_key(client)
    month_day = NOW.replace(day=1, hour=10)
    await log(org, key, month_day); await log(org, key, month_day, decision="error")
    for _ in range(4): await log(org, key, NOW - dt.timedelta(hours=1))
    assert await billable_this_month(org, NOW) == 5          # error excluded
    await purge_expired(NOW)                                  # the 1st (19 days old) is rolled up and deleted
    assert await count(RequestLog, org) == 4
    assert await billable_this_month(org, NOW) == 5          # still counts toward the month


async def test_old_rollup_from_previous_month_does_not_count(client):
    org, key = await org_and_key(client)
    await log(org, key, dt.datetime(2026, 9, 3, 12, tzinfo=dt.timezone.utc))
    await purge_expired(NOW)
    assert await billable_this_month(org, NOW) == 0


async def test_stale_pending_calls_are_settled_as_errors(client):
    org, key = await org_and_key(client)
    await log(org, key, NOW - dt.timedelta(minutes=20), decision="pending")   # the process died mid-call
    await log(org, key, NOW - dt.timedelta(minutes=2), decision="pending")    # still in flight
    res = await purge_expired(NOW)
    assert res["stale_settled"] == 1
    async with SessionLocal() as s:
        decisions = sorted((await s.execute(select(RequestLog.decision))).scalars().all())
    assert decisions == ["error", "pending"]
    assert await billable_this_month(org, NOW) == 1  # only the call that may still be running counts
