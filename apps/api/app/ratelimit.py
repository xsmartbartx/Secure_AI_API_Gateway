import logging
import time
import uuid
from collections import defaultdict, deque
from typing import Protocol

from app.config import settings

log = logging.getLogger("gateway.ratelimit")


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


# One round trip, atomic inside Redis: drop expired entries, count, and record this call only if there is room. Checking and
# recording in separate commands let parallel callers all pass the check before any recorded itself (28 calls got through a
# limit of 20 in a test with four workers). Redis's own clock is used so workers on different machines cannot disagree.
_SLIDING_WINDOW_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local window, limit = tonumber(ARGV[1]), tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
if redis.call('ZCARD', KEYS[1]) >= limit then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  local retry = 1
  if oldest[2] then retry = math.max(1, math.ceil(window - (now - tonumber(oldest[2])))) end
  return {0, retry}
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('EXPIRE', KEYS[1], math.ceil(window) + 5)
return {1, 0}
"""


class RedisSlidingWindow:
    """Sliding-window limiter shared by every API worker. If Redis cannot be reached the limiter fails open (and logs):
    a Redis outage must not take the whole API down, and the quota is enforced from the database either way."""

    def __init__(self, url: str, window: int = 60, max_connections: int = 100):
        import redis.asyncio as redis
        # A blocking pool waits briefly for a free connection instead of raising when a burst needs more than the pool holds.
        pool = redis.BlockingConnectionPool.from_url(url, max_connections=max_connections, timeout=2,
                                                     socket_timeout=2, socket_connect_timeout=2, health_check_interval=30)
        self.r = redis.Redis(connection_pool=pool)
        self.window = window
        self._script = self.r.register_script(_SLIDING_WINDOW_LUA)

    async def allow(self, key: str, limit: int) -> tuple[bool, int]:
        try:
            ok, retry = await self._script(keys=[f"rl:{key}"], args=[self.window, limit, uuid.uuid4().hex])
        except Exception:  # RedisError, timeouts, a dropped connection
            log.warning("rate limiter unavailable (Redis); allowing the call", exc_info=True)
            return True, 0
        return bool(ok), int(retry)


limiter: Limiter = RedisSlidingWindow(settings.REDIS_URL) if settings.REDIS_URL else MemorySlidingWindow()
