import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_gateway.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import datetime as dt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import ApiKey, Base, Organization, RequestLog, SessionLocal, engine
from app.main import app

A = {"x-dev-org": "org_u", "x-dev-user": "u"}
B = {"x-dev-org": "org_other", "x-dev-user": "o"}
NOW = dt.datetime.now(dt.timezone.utc)


@pytest.fixture(autouse=True)
async def fresh():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def mk(client, name, headers=A):
    return (await client.post("/api/keys", json={"name": name}, headers=headers)).json()


async def add(org_id, key_id, days_ago, model="m1", decision="allow", tin=10, tout=20):
    async with SessionLocal() as s:
        s.add(RequestLog(org_id=org_id, key_id=key_id, request_id="r", ts=NOW - dt.timedelta(days=days_ago), provider="mock", model=model,
                         status_code=200 if decision != "error" else 502, decision=decision, tokens_in=tin, tokens_out=tout))
        await s.commit()


async def seed(client):
    k1, k2 = await mk(client, "backend"), await mk(client, "=cmd|evil")
    org = (await client.get("/api/me", headers=A)).json()["org"]["id"]
    for _ in range(3): await add(org, k1["id"], 1)
    await add(org, k1["id"], 1, decision="error", tin=0, tout=0)
    await add(org, k1["id"], 40, model="m2")           # outside default 30d window
    await add(org, k2["id"], 2, model="m2", decision="block")
    await add(org, None, 1)                              # playground (no key)
    return org, k1, k2


async def test_group_by_key(client):
    org, k1, k2 = await seed(client)
    d = (await client.get("/api/usage?group=key", headers=A)).json()
    rows = {r["label"]: r for r in d["rows"]}
    assert rows["backend"]["calls"] == 4
    assert rows["backend"]["errors"] == 1
    assert rows["backend"]["tokens_in"] == 30
    assert rows["=cmd|evil"]["blocked"] == 1
    assert rows["Playground"]["calls"] == 1
    assert d["totals"]["calls"] == 6  # the 40-day-old row is outside the window
    assert rows["backend"]["id"] == k1["id"]
    assert rows["backend"]["prefix"].startswith("nx_live_")


async def test_group_by_model_and_day(client):
    await seed(client)
    m = (await client.get("/api/usage?group=model", headers=A)).json()
    assert {r["label"] for r in m["rows"]} == {"m1", "m2"}
    d = (await client.get("/api/usage?group=day", headers=A)).json()
    assert [r["label"] for r in d["rows"]] == sorted(r["label"] for r in d["rows"])  # chronological
    assert sum(r["calls"] for r in d["rows"]) == d["totals"]["calls"]


async def test_date_range_inclusive(client):
    org, k1, _ = await seed(client)
    day40 = (NOW - dt.timedelta(days=40)).date().isoformat()
    r = (await client.get(f"/api/usage?group=key&from={day40}&to={day40}", headers=A)).json()
    assert r["totals"]["calls"] == 1
    assert r["rows"][0]["label"] == "backend"
    today = NOW.date().isoformat()
    r = (await client.get(f"/api/usage?group=day&from={today}&to={today}", headers=A)).json()
    assert r["totals"]["calls"] == 0
    assert r["rows"] == []


async def test_validation(client):
    assert (await client.get("/api/usage?from=2026-02-01&to=2026-01-01", headers=A)).status_code == 422
    assert (await client.get("/api/usage?from=2020-01-01&to=2026-01-01", headers=A)).status_code == 422  # > 366 days
    assert (await client.get("/api/usage?group=nonsense", headers=A)).status_code == 422
    assert (await client.get("/api/usage?from=notadate", headers=A)).status_code == 422


async def test_isolated_per_org(client):
    await seed(client)
    r = (await client.get("/api/usage?group=key", headers=B)).json()
    assert r["rows"] == []
    assert r["totals"]["calls"] == 0


async def test_deleted_key_labelled(client):
    org, k1, _ = await seed(client)
    async with SessionLocal() as s:
        for l in (await s.execute(select(RequestLog).where(RequestLog.key_id == k1["id"]))).scalars():
            l.key_id = None  # what ON DELETE SET NULL does
        await s.commit()
    rows = {r["label"] for r in (await client.get("/api/usage?group=key", headers=A)).json()["rows"]}
    assert "Playground" in rows  # unattributed calls are grouped, never dropped


async def test_csv_export_neutralises_formulas(client):
    await seed(client)
    r = await client.get("/api/usage?group=key&format=csv", headers=A)
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("label,")
    assert any(l.startswith("'=cmd|evil,") for l in lines)
    assert "attachment" in r.headers["content-disposition"]
