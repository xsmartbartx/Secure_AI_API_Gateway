import asyncio
import datetime as dt
import hashlib
import json
import logging
import time
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.anthropic_adapter import AnthropicAdapter
from app.adapters.mock_adapter import MockAdapter
from app.adapters.openai_adapter import OpenAIAdapter
from app.config import settings
from app import policy, providers
from app.db import ApiKey, Organization, ProviderConnection, RequestLog, SecurityEvent, SessionLocal, get_session
from app.deps import get_api_key
from app.usage import billable_this_month
from app.errors import GatewayError
from app.ratelimit import limiter
from app.schemas import StreamEvent, UnifiedChatRequest, UnifiedChatResponse

router = APIRouter()
log = logging.getLogger("gateway.data")
FLAG_CODES = {"provider_auth_failed", "provider_credentials_unreadable"}  # errors that mean a saved key no longer works
# Every call has an end-to-end deadline, and both are well under retention.STALE_PENDING_MINUTES (15 min). A call still running is
# therefore never mistaken for an abandoned one when stale reservations are settled.
MAX_CALL_SECONDS = 300      # a non-streaming call, or the first chunk of a stream
MAX_STREAM_SECONDS = 540    # a whole stream

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
    raise GatewayError(502, "upstream_not_configured", "No model provider is configured. Add your own API key under Providers.")


@router.get("/v1/health")
async def health():
    return {"status": "operational"}


def _upstream_timeout() -> GatewayError:
    return GatewayError(504, "upstream_timeout", "The provider took too long to answer. The call was not counted.")


def _invalid_upstream() -> GatewayError:
    return GatewayError(502, "upstream_invalid_response", "The provider answered in a way Gateway could not read. The call was not counted.")


async def _flag_connection(conn_id: str | None, code: str) -> None:
    """A saved provider key stopped working (revoked, expired, unreadable): show it as failing on the Providers page."""
    if conn_id and code in FLAG_CODES:
        async with SessionLocal() as s:
            c = await s.get(ProviderConnection, conn_id)
            if c:
                c.status = "failing"
                await s.commit()


async def _resolve_upstream(session: AsyncSession, org_id: str, body: UnifiedChatRequest) -> tuple[str, str | None, str | None]:
    """(provider, credential, connection id): the org's own key if it has one, else the shared platform key (or the dev mock)."""
    conn = await providers.resolve_connection(session, org_id, body.provider)
    if conn is None:
        return pick_provider(body), None, None
    try:
        return conn.provider, providers.decrypt_credential(conn.credential_enc, providers.aad_for(conn)), conn.id
    except (ValueError, InvalidTag):  # corrupted, or encrypted under a key that is no longer configured
        await _flag_connection(conn.id, "provider_credentials_unreadable")
        raise GatewayError(502, "provider_credentials_unreadable", "Your saved provider key can't be read any more. Add it again under Providers.") from None


def _quota_error() -> GatewayError:
    return GatewayError(429, "quota_exceeded", "Monthly call quota reached. Upgrade your plan to continue.", {"Retry-After": "3600"})


@dataclass
class Prepared:
    """A call that passed every check and is reserved: the log row, the credential to use, and what to settle at the end."""
    entry: RequestLog
    credential: str | None
    conn_id: str | None
    flagged: bool  # a monitor-mode policy would have blocked it

    @property
    def final_decision(self) -> str:
        return "flag" if self.flagged else "allow"


async def _block_by_policy(session: AsyncSession, entry: RequestLog, verdict: policy.Verdict) -> GatewayError:
    """Record a call the org's policy refused (nothing was sent upstream, so it is neither billed nor counted toward quota)."""
    entry.decision, entry.status_code, entry.latency_ms = "block", 403, 0
    session.add(entry)
    await session.flush()
    session.add(SecurityEvent(org_id=entry.org_id, log_id=entry.id, type="policy_denied", severity="medium", rule_id=verdict.rule,
                              redacted_excerpt=f"model: {entry.model}"))
    await session.commit()
    return GatewayError(403, "model_not_allowed", f"The model '{entry.model}' is not allowed by your organization's policy.")


async def _preflight(request: Request, body: UnifiedChatRequest, key: ApiKey, session: AsyncSession, track_key: bool) -> Prepared:
    """Rate limit, quota, provider and policy checks, then reserve the call. Raises GatewayError before anything is sent upstream."""
    ok, retry = await limiter.allow(key.id, key.rpm_limit)
    if not ok:
        raise GatewayError(429, "rate_limited", "Too many requests for this key.", {"Retry-After": str(retry)})
    org = await session.get(Organization, key.org_id)
    if await billable_this_month(key.org_id, s=session) >= org.monthly_call_quota:  # cheap early exit
        raise _quota_error()
    provider, credential, conn_id = await _resolve_upstream(session, key.org_id, body)
    body.model = body.model or DEFAULT_MODEL[provider]  # the effective model is what the policy judges
    prompt_hash = hashlib.sha256("\n".join(m.content for m in body.messages).encode()).hexdigest()
    entry = RequestLog(org_id=key.org_id, key_id=key.id if track_key else None, request_id=request.state.request_id,
                       provider=provider, model=body.model, status_code=200, decision="pending", prompt_hash=prompt_hash)
    verdict = await policy.check_model(session, key.org_id, body.model)
    if verdict.action == "block":
        raise await _block_by_policy(session, entry, verdict)
    # Reserve first, then verify. The call is committed as "pending" before anything is sent upstream, so requests that run at
    # the same time see each other; one that would take the org over its quota backs out. (Counting first and writing the
    # row after the upstream answers let a burst of in-flight calls all read the same count.)
    session.add(entry)
    await session.flush()
    if verdict.action == "flag":
        session.add(SecurityEvent(org_id=entry.org_id, log_id=entry.id, type="policy_would_deny", severity="low", rule_id=verdict.rule,
                                  redacted_excerpt=f"model: {entry.model}"))
    await session.commit()
    if await billable_this_month(key.org_id, s=session) > org.monthly_call_quota:
        await session.execute(delete(SecurityEvent).where(SecurityEvent.log_id == entry.id))
        await session.delete(entry)
        await session.commit()
        raise _quota_error()
    return Prepared(entry, credential, conn_id, verdict.action == "flag")


async def _chat(request: Request, body: UnifiedChatRequest, key: ApiKey, session: AsyncSession, track_key: bool = True) -> UnifiedChatResponse:
    prep = await _preflight(request, body, key, session, track_key)
    entry, started = prep.entry, time.monotonic()
    try:
        result = await asyncio.wait_for(ADAPTERS[entry.provider].execute_chat(body, prep.credential), MAX_CALL_SECONDS)
        entry.tokens_in, entry.tokens_out, entry.decision = result.usage.prompt_tokens, result.usage.completion_tokens, prep.final_decision
        return result
    except GatewayError as e:
        entry.status_code, entry.decision = e.status, "error"
        await _flag_connection(prep.conn_id, e.code)
        raise
    except TimeoutError:
        entry.status_code, entry.decision = 504, "error"
        raise _upstream_timeout() from None
    except Exception as e:  # a malformed upstream response must not be logged, or billed, as a success
        log.exception("could not process the %s response", entry.provider)
        entry.status_code, entry.decision = 502, "error"
        raise _invalid_upstream() from e
    finally:
        entry.latency_ms = int((time.monotonic() - started) * 1000)
        if track_key:
            key.last_used_at = dt.datetime.now(dt.timezone.utc)
            session.add(key)
        session.add(entry)
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
        await s.merge(log)  # the call was reserved as a row by the request's own session; update it
        if key_id:
            k = await s.get(ApiKey, key_id)
            if k:
                k.last_used_at = dt.datetime.now(dt.timezone.utc)
        await s.commit()


def _error_event(rid: str, err: GatewayError) -> str:
    return f"data: {json.dumps({'error': {'code': err.code, 'message': err.message, 'request_id': rid}})}\n\n"


def _settle_stream(entry: RequestLog, body: UnifiedChatRequest, started: float, p_tokens: int | None, c_tokens: int | None, emitted: int, final: str) -> None:
    """Final numbers for a stream's log row. Token counts are the provider's when it reported them, else an estimate (chars / 4)."""
    est_in = sum(len(m.content) for m in body.messages) // 4 + 1
    entry.tokens_in = p_tokens if p_tokens is not None else est_in
    entry.tokens_out = c_tokens if c_tokens is not None else emitted // 4 + (1 if emitted else 0)
    entry.latency_ms = int((time.monotonic() - started) * 1000)
    if entry.decision == "pending":  # finished normally, or the client left: the call happened and counts
        entry.decision = final


async def _sse(first: StreamEvent | None, gen, body: UnifiedChatRequest, entry: RequestLog, key_id: str | None, started: float, final: str = "allow"):
    """Yields OpenAI-style chunks. Always settles exactly one log row, even if the client disconnects mid-stream."""
    rid, p_tokens, c_tokens, emitted, finish = entry.request_id, None, None, 0, None
    try:
        yield _chunk(rid, entry.model, {"role": "assistant"})
        pending = [first] if first is not None else []
        while True:
            left = MAX_STREAM_SECONDS - (time.monotonic() - started)
            ev = pending.pop() if pending else await asyncio.wait_for(gen.__anext__(), max(left, 0.001))
            if ev.type == "delta":
                emitted += len(ev.text)
                yield _chunk(rid, entry.model, {"content": ev.text})
            elif ev.type == "usage":
                p_tokens = ev.prompt_tokens if ev.prompt_tokens is not None else p_tokens
                c_tokens = ev.completion_tokens if ev.completion_tokens is not None else c_tokens
            elif ev.type == "finish":
                finish = ev.finish_reason
    except StopAsyncIteration:
        pass
    except Exception as e:  # upstream failed after the stream began: say so in-band, then close
        err = e if isinstance(e, GatewayError) else GatewayError(504, "stream_timeout", "The response took too long and was stopped.") if isinstance(e, TimeoutError) else _invalid_upstream()
        if err is not e and not isinstance(e, TimeoutError):
            log.exception("could not process the %s stream", entry.provider)
        entry.status_code, entry.decision = err.status, "error"
        yield _error_event(rid, err)
        return
    except (asyncio.CancelledError, GeneratorExit):  # client went away
        entry.status_code = 499
        raise
    finally:
        _settle_stream(entry, body, started, p_tokens, c_tokens, emitted, final)
        await asyncio.shield(_write_log(entry, key_id))
        try:
            await gen.aclose()
        except Exception:
            pass
    usage = {"prompt_tokens": entry.tokens_in, "completion_tokens": entry.tokens_out, "total_tokens": entry.tokens_in + entry.tokens_out}
    yield _chunk(rid, entry.model, {}, finish or "stop", usage)
    yield "data: [DONE]\n\n"


async def _chat_stream(request: Request, body: UnifiedChatRequest, key: ApiKey, session: AsyncSession, track_key: bool = True):
    prep = await _preflight(request, body, key, session, track_key)
    entry, conn_id, started = prep.entry, prep.conn_id, time.monotonic()
    gen = ADAPTERS[entry.provider].stream_chat(body, prep.credential)
    key_id = key.id if track_key else None
    try:
        first = await asyncio.wait_for(gen.__anext__(), MAX_CALL_SECONDS)  # surfaces upstream refusals as a normal HTTP error before any byte is sent
    except StopAsyncIteration:
        first = None
    except Exception as e:
        err = e if isinstance(e, GatewayError) else _upstream_timeout() if isinstance(e, TimeoutError) else _invalid_upstream()
        entry.status_code, entry.decision = err.status, "error"
        entry.latency_ms = int((time.monotonic() - started) * 1000)
        await _flag_connection(conn_id, err.code)
        await _write_log(entry, key_id)
        if err is e:
            raise
        if not isinstance(e, TimeoutError):
            log.exception("could not process the %s stream", entry.provider)
        raise err from e
    return StreamingResponse(_sse(first, gen, body, entry, key_id, started, prep.final_decision), media_type="text/event-stream",
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
