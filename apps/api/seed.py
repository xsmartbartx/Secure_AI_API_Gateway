"""Dev seed: fake org, key and calls so every dashboard screen has data. Run: python seed.py"""
import asyncio, random, datetime as dt
from app.db import ApiKey, Organization, RequestLog, SessionLocal, init_db
from app.keys import generate_key

async def main():
    await init_db()
    async with SessionLocal() as s:
        org = Organization(external_org_id="org_demo", name="Demo org", monthly_call_quota=100)
        s.add(org); await s.flush()
        secret, prefix, h, last4 = generate_key()
        k = ApiKey(org_id=org.id, name="demo-backend", prefix=prefix, key_hash=h, last4=last4)
        s.add(k); await s.flush()
        now = dt.datetime.now(dt.timezone.utc)
        for i in range(60):
            d = random.choice(["allow"] * 9 + ["error"])
            s.add(RequestLog(org_id=org.id, key_id=k.id, request_id=f"req_seed{i:04d}", ts=now - dt.timedelta(hours=random.randint(0, 150)),
                provider="mock", model="mock-1", status_code=200 if d == "allow" else 502, decision=d,
                tokens_in=random.randint(20, 400), tokens_out=random.randint(20, 600), latency_ms=random.randint(180, 1800)))
        await s.commit()
    print("Seeded org_demo. Demo key (shown once):", secret)

asyncio.run(main())
