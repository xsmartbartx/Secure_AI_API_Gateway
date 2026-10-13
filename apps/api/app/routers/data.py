import datetime as dt
import hashlib
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.anthropic_adapter import AnthropicAdapter
from app.adapters.mock_adapter import MockAdapter
from app.adapters.openai_adapter import OpenAIAdapter
from app.config import settings
from app.db import ApiKey, Organization, RequestLog, get_session
from app.deps import get_api_key, month_start
from app.errors import GatewayError
from app.ratelimit import limiter
from app.schemas import UnifiedChatRequest, UnifiedChatResponse

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


async def _chat(request: Request, body: UnifiedChatRequest, key: ApiKey, session: AsyncSession, track_key: bool = True) -> UnifiedChatResponse:
    rid = request.state.request_id
    if body.stream:
        raise GatewayError(422, "stream_not_supported", "Streaming is not available yet. Set stream to false.")

    ok, retry = await limiter.allow(key.id, key.rpm_limit)
    if not ok:
        raise GatewayError(429, "rate_limited", "Too many requests for this key.", {"Retry-After": str(retry)})

    org = await session.get(Organization, key.org_id)
    used = (await session.execute(
        select(func.count()).select_from(RequestLog).where(
            RequestLog.org_id == key.org_id, RequestLog.ts >= month_start(), RequestLog.decision != "error")
    )).scalar_one()
    if used >= org.monthly_call_quota:
        raise GatewayError(429, "quota_exceeded", "Monthly call quota reached. Upgrade your plan to continue.",
                           {"Retry-After": "3600"})

    provider = pick_provider(body)
    body.model = body.model or DEFAULT_MODEL[provider]
    started = time.monotonic()
    prompt_hash = hashlib.sha256("\n".join(m.content for m in body.messages).encode()).hexdigest()
    log = RequestLog(org_id=key.org_id, key_id=key.id if track_key else None, request_id=rid, provider=provider, model=body.model,
                     status_code=200, decision="allow", prompt_hash=prompt_hash)
    try:
        result = await ADAPTERS[provider].execute_chat(body)
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


@router.post("/v1/chat", response_model=UnifiedChatResponse)
async def chat(request: Request, body: UnifiedChatRequest, key: ApiKey = Depends(get_api_key),
               session: AsyncSession = Depends(get_session)):
    return await _chat(request, body, key, session)


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, body: UnifiedChatRequest, key: ApiKey = Depends(get_api_key),
                           session: AsyncSession = Depends(get_session)):
    r = await _chat(request, body, key, session)
    return {
        "id": r.id, "object": "chat.completion", "model": r.model,
        "choices": [{"index": c.index, "message": c.message.model_dump(), "finish_reason": c.finish_reason} for c in r.choices],
        "usage": r.usage.model_dump(),
    }
