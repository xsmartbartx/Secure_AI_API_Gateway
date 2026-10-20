"""Shared helpers for provider adapters that speak server-sent events."""
import json
from typing import AsyncIterator, Callable

import httpx

from app.errors import GatewayError


async def check_stream_status(r: httpx.Response, provider: str, auth_error: Callable[[], GatewayError]) -> None:
    """Refuse before any byte is streamed to the caller: a rejected key or an upstream error becomes a normal HTTP error."""
    if r.status_code in (401, 403):
        raise auth_error()
    if r.status_code >= 400:
        body = (await r.aread()).decode(errors="replace")
        raise GatewayError(502, "upstream_error", f"{provider} Error ({r.status_code}): {body}"[:500])


async def sse_json(r: httpx.Response) -> AsyncIterator[dict]:
    """The decoded JSON object of every `data:` line. Stops at `[DONE]`; lines that are not JSON objects are skipped."""
    async for line in r.aiter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def raise_for_status(exc: httpx.HTTPStatusError, provider: str, auth_error: Callable[[], GatewayError]) -> GatewayError:
    """The gateway error for a failed non-streaming call."""
    if exc.response.status_code in (401, 403):
        return auth_error()
    return GatewayError(502, "upstream_error", f"{provider} Error: {exc.response.text}"[:500])
