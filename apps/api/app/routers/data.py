import asyncio
import datetime as dt
import hashlib
import json
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.anthropic_adapter import AnthropicAdapter
from app.adapters.mock_adapter import MockAdapter
from app.adapters.openai_adapter import OpenAIAdapter
from app.config import settings
from app.db import ApiKey, Organization, RequestLog, SessionLocal, get_session
from app.deps import get_api_key
from app.usage import billable_this_month
from app.errors import GatewayError
from app.ratelimit import limiter
from app.schemas import StreamEvent, UnifiedChatRequest, UnifiedChatResponse

router = APIRouter()

ADAPTERS = {"anthropic": AnthropicAdapter(), "openai": OpenAIAdapter(), "mock": MockAdapter()}
DEFAULT_MODEL = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4o", "mock": "mock-1"}


def pick_provider(req: UnifiedChatRequest) -> str:
    if req.provider:
        p = req.provider.lower()
        if p not in ADAPTERS or (p == "mock" and settings.ENV == "prod"):
            raise GatewayError(422, "unknown_provider", f"Provider '{req.provider}' is not available.")
        return p
    if settings.ANTHROPIC_API_KEY:
        return "anthropic"
    if settings.OPENAI_API_KEY:
        return "openai"
    if settings.ALLOW_MOCK_UPSTREAM and settings.ENV != "prod":
        return "mock"
    raise GatewayError(502, "upstream_not_configured", "No upstream provider is configured.")


@router.get("/v1/health")
async def health():
    return {"status": "operational"}


async def _preflight(request: Request, body: UnifiedChatRequest, key: ApiKey, session: AsyncSession, track_key: bool):
    """Rate limit, quota, provider choice. Raises GatewayError before anything is sent upstream."""
    ok, retry = await limiter.allow(key.id, key.rpm_limit)
    if not ok:
        raise GatewayError(429, "rate_limited", "Too many requests for this key.", {"Retry-After": str(retry)})
    org = await session.get(Organization, key.org_id)
    used = await billable_this_month(key.org_id, s=session)
    if used >= org.monthly_call_quota:
        raise GatewayError(429, "quota_exceeded", "Monthly call quota reached. Upgrade your plan to continue.", {"Retry-After": "3600"})
    provider = pick_provider(body)
    body.model = body.model or DEFAULT_MODEL[provider]
    prompt_hash = hashlib.sha256("\n".join(m.content for m in body.messages).encode()).hexdigest()
    return RequestLog(org_id=key.org_id, key_id=key.id if track_key else None, request_id=request.state.request_id,
                      provider=provider, model=body.model, status_code=200, decision="allow", prompt_hash=prompt_hash)


async def _chat(request: Request, body: UnifiedChatRequest, key: ApiKey, session: AsyncSession, track_key: bool = True) -> UnifiedChatResponse:
    log = await _preflight(request, body, key, session, track_key)
    started = time.monotonic()
    try:
        result = await ADAPTERS[log.provider].execute_chat(body)
        log.tokens_in, log.tokens_out = result.usage.prompt_tokens, result.usage.completion_tokens
        return result
    except GatewayError as e:
        log.status_code, log.decision = e.status, "error"
        raise
    finally:
        log.latency_ms = int((time.monotonic() - started) * 1000)
        if track_key:
            key.last_used_at = dt.datetime.now(dt.timezone.utc)
            session.add(key)
        session.add(log)
        await session.commit()


# ---------- streaming ----------

def _chunk(rid: str, model: str, delta: dict, finish: str | None = None, usage: dict | None = None) -> str:
    obj = {"id": rid, "object": "chat.completion.chunk", "model": model,
           "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage is not None:
        obj["usage"] = usage
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


async def _write_log(log: RequestLog, key_id: str | None) -> None:
    """The request's DB session is gone once the response has started, so streams log through their own."""
    async with SessionLocal() as s:
        s.add(log)
        if key_id:
            k = await s.get(ApiKey, key_id)
            if k:
                k.last_used_at = dt.datetime.now(dt.timezone.utc)
        await s.commit()


async def _sse(first: StreamEvent | None, gen, body: UnifiedChatRequest, log: RequestLog, key_id: str | None, started: float):
    """Yields OpenAI-style chunks. Always writes exactly one log row, even if the client disconnects mid-stream."""
    rid, p_tokens, c_tokens, emitted, finish = log.request_id, None, None, 0, None
    try:
        yield _chunk(rid, log.model, {"role": "assistant"})
        pending = [first] if first is not None else []
        while True:
            ev = pending.pop() if pending else await gen.__anext__()
            if ev.type == "delta":
                emitted += len(ev.text)
                yield _chunk(rid, log.model, {"content": ev.text})
            elif ev.type == "usage":
                p_tokens = ev.prompt_tokens if ev.prompt_tokens is not None else p_tokens
                c_tokens = ev.completion_tokens if ev.completion_tokens is not None else c_tokens
            elif ev.type == "finish":
                finish = ev.finish_reason
    except StopAsyncIteration:
        pass
    except GatewayError as e:  # upstream failed after the stream began: say so in-band, then close
        log.status_code, log.decision = e.status, "error"
        yield f"data: {json.dumps({'error': {'code': e.code, 'message': e.message, 'request_id': rid}})}\n\n"
        return
    except (asyncio.CancelledError, GeneratorExit):  # client went away; the call still happened and still counts
        log.status_code = 499
        raise
    finally:
        est_in = sum(len(m.content) for m in body.messages) // 4 + 1
        log.tokens_in = p_tokens if p_tokens is not None else est_in
        log.tokens_out = c_tokens if c_tokens is not None else emitted // 4 + (1 if emitted else 0)
        log.latency_ms = int((time.monotonic() - started) * 1000)
        await asyncio.shield(_write_log(log, key_id))
        try:
            await gen.aclose()
        except Exception:
            pass
    usage = {"prompt_tokens": log.tokens_in, "completion_tokens": log.tokens_out, "total_tokens": log.tokens_in + log.tokens_out}
    yield _chunk(rid, log.model, {}, finish or "stop", usage)
    yield "data: [DONE]\n\n"


async def _chat_stream(request: Request, body: UnifiedChatRequest, key: ApiKey, session: AsyncSession, track_key: bool = True):
    log = await _preflight(request, body, key, session, track_key)
    started = time.monotonic()
    gen = ADAPTERS[log.provider].stream_chat(body)
    try:
        first = await gen.__anext__()  # surfaces upstream refusals as a normal HTTP error before any byte is sent
    except StopAsyncIteration:
        first = None
    except GatewayError as e:
        log.status_code, log.decision = e.status, "error"
        log.latency_ms = int((time.monotonic() - started) * 1000)
        await _write_log(log, key.id if track_key else None)
        raise
    return StreamingResponse(
        _sse(first, gen, body, log, key.id if track_key else None, started), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/v1/chat")
async def chat(request: Request, body: UnifiedChatRequest, key: ApiKey = Depends(get_api_key),
               session: AsyncSession = Depends(get_session)):
    if body.stream:
        return await _chat_stream(request, body, key, session)
    return await _chat(request, body, key, session)


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, body: UnifiedChatRequest, key: ApiKey = Depends(get_api_key),
                           session: AsyncSession = Depends(get_session)):
    if body.stream:
        return await _chat_stream(request, body, key, session)
    r = await _chat(request, body, key, session)
    return {
        "id": r.id, "object": "chat.completion", "model": r.model,
        "choices": [{"index": c.index, "message": c.message.model_dump(), "finish_reason": c.finish_reason} for c in r.choices],
        "usage": r.usage.model_dump(),
    }
