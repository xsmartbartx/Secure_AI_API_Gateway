import json

import httpx
from app.errors import GatewayError
from app.adapters.base import BaseProviderAdapter
from app.schemas import StreamEvent, UnifiedChatRequest, UnifiedChatResponse, ChatChoice, ChatMessage, UsageInfo
from app.config import settings

def _auth() -> GatewayError:
    return GatewayError(502, "provider_auth_failed", "OpenAI rejected the API key. Check it under Providers.")


class OpenAIAdapter(BaseProviderAdapter):
    name = 'openai'

    def __init__(self):
        self.url = "https://api.openai.com/v1/chat/completions"

    async def execute_chat(self, request: UnifiedChatRequest, credential: str | None = None) -> UnifiedChatResponse:
        api_key = credential or settings.OPENAI_API_KEY
        if not api_key:
            raise GatewayError(
                502, 'upstream_not_configured', "OpenAI upstream provider credentials missing from Gateway. Add your own key under Providers.")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": request.model,
            "messages": [msg.model_dump() for msg in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        async with httpx.AsyncClient(transport=self.transport) as client:
            try:
                response = await client.post(self.url, json=payload, headers=headers, timeout=60.0)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (401, 403):
                    raise _auth()
                raise GatewayError(502, 'upstream_error', f"OpenAI Error: {exc.response.text}"[:500])
            except httpx.RequestError as exc:
                raise GatewayError(502, 'upstream_unreachable', f"Network unreachable: {str(exc)}")

        data = response.json()
        
        choices = [
            ChatChoice(
                index=c.get("index", 0),
                message=ChatMessage(
                    role=c.get("message", {}).get("role", "assistant"),
                    content=c.get("message", {}).get("content", "")
                ),
                finish_reason=c.get("finish_reason")
            ) for c in data.get("choices", [])
        ]

        usage = UsageInfo(
            prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
            total_tokens=data.get("usage", {}).get("total_tokens", 0)
        )

        return UnifiedChatResponse(id=data.get("id", "unk"), provider="openai", model=data.get("model", request.model), choices=choices, usage=usage)

    async def stream_chat(self, request: UnifiedChatRequest, credential: str | None = None):
        api_key = credential or settings.OPENAI_API_KEY
        if not api_key:
            raise GatewayError(502, "upstream_not_configured", "OpenAI upstream provider credentials missing from Gateway. Add your own key under Providers.")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": request.model, "messages": [m.model_dump() for m in request.messages],
                   "temperature": request.temperature, "stream": True, "stream_options": {"include_usage": True}}
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        async with httpx.AsyncClient(transport=self.transport) as client:
            try:
                async with client.stream("POST", self.url, json=payload, headers=headers, timeout=httpx.Timeout(60.0, read=120.0)) as r:
                    if r.status_code in (401, 403):
                        raise _auth()
                    if r.status_code >= 400:
                        body = (await r.aread()).decode(errors="replace")
                        raise GatewayError(502, "upstream_error", f"OpenAI Error ({r.status_code}): {body}"[:500])
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
                        for c in obj.get("choices") or []:
                            text = (c.get("delta") or {}).get("content")
                            if text:
                                yield StreamEvent(type="delta", text=text)
                            if c.get("finish_reason"):
                                yield StreamEvent(type="finish", finish_reason=c["finish_reason"])
                        if obj.get("usage"):
                            u = obj["usage"]
                            yield StreamEvent(type="usage", prompt_tokens=u.get("prompt_tokens", 0), completion_tokens=u.get("completion_tokens", 0))
            except httpx.RequestError as exc:
                raise GatewayError(502, "upstream_unreachable", f"Network unreachable: {exc}")
