"""The Redis rate limiter against a real Redis. Skipped unless REDIS_TEST_URL is set, e.g.
    REDIS_TEST_URL=redis://127.0.0.1:56379/15 pytest tests/test_redis_limiter.py
The database number is flushed, so point it at a throwaway Redis."""
import asyncio
import os
import time

import pytest

from app.ratelimit import RedisSlidingWindow

URL = os.environ.get("REDIS_TEST_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="REDIS_TEST_URL is not set")


@pytest.fixture
async def limiter():
    lim = RedisSlidingWindow(URL, window=60)
    await lim.r.flushdb()
    yield lim
    await lim.r.flushdb()
    await lim.close()


async def test_a_parallel_burst_is_admitted_exactly_up_to_the_limit(limiter):
    results = await asyncio.gather(*[limiter.allow("k", 20) for _ in range(100)])
    assert sum(ok for ok, _ in results) == 20


async def test_two_limiters_share_one_budget_like_two_workers(limiter):
    other = RedisSlidingWindow(URL, window=60)
    try:
        results = await asyncio.gather(*[(limiter if i % 2 else other).allow("k", 30) for i in range(120)])
        assert sum(ok for ok, _ in results) == 30
    finally:
        await other.close()


async def test_the_retry_hint_is_within_the_window(limiter):
    for _ in range(5):
        await limiter.allow("k", 5)
    ok, retry = await limiter.allow("k", 5)
    assert ok is False
    assert 1 <= retry <= 60


async def test_keys_are_independent(limiter):
    assert all([(await limiter.allow("a", 2))[0], (await limiter.allow("a", 2))[0]])
    assert (await limiter.allow("a", 2))[0] is False
    assert (await limiter.allow("b", 2))[0] is True


async def test_the_window_slides(limiter):
    short = RedisSlidingWindow(URL, window=1)
    try:
        await short.r.flushdb()
        assert [(await short.allow("k", 2))[0] for _ in range(3)] == [True, True, False]
        await asyncio.sleep(1.2)
        assert (await short.allow("k", 2))[0] is True
    finally:
        await short.close()


async def test_idle_keys_expire_so_redis_does_not_fill_up(limiter):
    await limiter.allow("k", 5)
    ttl = await limiter.r.ttl("rl:k")
    assert 0 < ttl <= 65


async def test_the_limiter_survives_a_burst_faster_than_the_old_check_then_add(limiter):
    t = time.perf_counter()
    await asyncio.gather(*[limiter.allow(f"k{i % 10}", 5) for i in range(500)])
    assert time.perf_counter() - t < 5


async def test_an_unreachable_redis_fails_open_quickly_instead_of_raising():
    dead = RedisSlidingWindow("redis://127.0.0.1:1/0", window=60)       # nothing listens on port 1
    try:
        t = time.perf_counter()
        assert await dead.allow("k", 5) == (True, 0)
        assert time.perf_counter() - t < 5
    finally:
        await dead.close()


async def test_fail_closed_callers_are_denied_when_redis_is_down():
    dead = RedisSlidingWindow("redis://127.0.0.1:1/0", window=60)
    try:
        assert await dead.allow("alert:o:k", 1, fail_open=False) == (False, 60)
    finally:
        await dead.close()
