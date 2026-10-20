import time
import uuid
from collections import defaultdict, deque
from typing import Protocol

from app.config import settings


class Limiter(Protocol):
    async def allow(self, key: str, limit: int) -> tuple[bool, int]: ...


class MemorySlidingWindow:
    """Single-process limiter for dev/tests. Not safe across workers; production sets REDIS_URL."""

    def __init__(self, window: int = 60):
        self.window = window
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def allow(self, key: str, limit: int) -> tuple[bool, int]:  # NOSONAR: async to match the Limiter interface (the Redis limiter awaits)
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= limit:
            return False, max(1, int(self.window - (now - q[0])))
        q.append(now)
        return True, 0


class RedisSlidingWindow:
    """Sorted-set sliding window shared by every API worker."""

    def __init__(self, url: str, window: int = 60):
        import redis.asyncio as redis
        self.r = redis.from_url(url)
        self.window = window

    async def allow(self, key: str, limit: int) -> tuple[bool, int]:
        k, now = f"rl:{key}", time.time()
        pipe = self.r.pipeline()
        pipe.zremrangebyscore(k, 0, now - self.window)
        pipe.zcard(k)
        _, count = await pipe.execute()
        if count >= limit:
            oldest = await self.r.zrange(k, 0, 0, withscores=True)
            retry = max(1, int(self.window - (now - oldest[0][1]))) if oldest else 1
            return False, retry
        pipe = self.r.pipeline()
        pipe.zadd(k, {uuid.uuid4().hex: now})
        pipe.expire(k, self.window + 5)
        await pipe.execute()
        return True, 0


limiter: Limiter = RedisSlidingWindow(settings.REDIS_URL) if settings.REDIS_URL else MemorySlidingWindow()
