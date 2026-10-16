import json

import httpx
from app.errors import GatewayError
from app.adapters.base import BaseProviderAdapter
from app.schemas import StreamEvent, UnifiedChatRequest, UnifiedChatResponse, ChatChoice, ChatMessage, UsageInfo
from app.config import settings

def _auth() -> GatewayError:
    return GatewayError(502, "provider_auth_failed", "Anthropic rejected the API key. Check it under Providers.")


class AnthropicAdapter(BaseProviderAdapter):
    name = 'anthropic'

    def __init__(self):
        self.url = "https://api.anthropic.com/v1/messages"

    async def execute_chat(self, request: UnifiedChatRequest, credential: str | None = None) -> UnifiedChatResponse:
        api_key = credential or settings.ANTHROPIC_API_KEY
        if not api_key:
            raise GatewayError(
                502, 'upstream_not_configured', "Anthropic upstream provider credentials missing from Gateway. Add your own key under Providers.")

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        # Adapt system roles cleanly for Anthropic structures
        system_content = None
        messages_payload = []
        for msg in request.messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                messages_payload.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": request.model,
            "messages": messages_payload,
            "max_tokens": request.max_tokens or 1024,
            "temperature": request.temperature
        }
        if system_content:
            payload["system"] = system_content

        async with httpx.AsyncClient(transport=self.transport) as client:
            try:
                response = await client.post(self.url, json=payload, headers=headers, timeout=60.0)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (401, 403):
                    raise _auth()
                raise GatewayError(502, 'upstream_error', f"Anthropic Error: {exc.response.text}"[:500])
            except httpx.RequestError as exc:
                raise GatewayError(502, 'upstream_unreachable', f"Network unreachable: {str(exc)}")

        data = response.json()
        
        text_response = "".join([block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"])
        
        choices = [
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content=text_response),
                finish_reason=data.get("stop_reason")
            )
        ]

        u = data.get("usage", {})
        usage = UsageInfo(
            prompt_tokens=u.get("input_tokens", 0),
            completion_tokens=u.get("output_tokens", 0),
            total_tokens=u.get("input_tokens", 0) + u.get("output_tokens", 0)
        )

        return UnifiedChatResponse(id=data.get("id", "unk"), provider="anthropic", model=data.get("model", request.model), choices=choices, usage=usage)

    async def stream_chat(self, request: UnifiedChatRequest, credential: str | None = None):
        api_key = credential or settings.ANTHROPIC_API_KEY
        if not api_key:
            raise GatewayError(502, "upstream_not_configured", "Anthropic upstream provider credentials missing from Gateway. Add your own key under Providers.")
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        system, msgs = None, []
        for m in request.messages:
            if m.role == "system":
                system = m.content
            else:
                msgs.append({"role": m.role, "content": m.content})
        payload = {"model": request.model, "messages": msgs, "max_tokens": request.max_tokens or 1024,
                   "temperature": request.temperature, "stream": True}
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(transport=self.transport) as client:
            try:
                async with client.stream("POST", self.url, json=payload, headers=headers, timeout=httpx.Timeout(60.0, read=120.0)) as r:
                    if r.status_code in (401, 403):
                        raise _auth()
                    if r.status_code >= 400:
                        body = (await r.aread()).decode(errors="replace")
                        raise GatewayError(502, "upstream_error", f"Anthropic Error ({r.status_code}): {body}"[:500])
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            obj = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        kind = obj.get("type")
                        if kind == "message_start":
                            u = (obj.get("message") or {}).get("usage") or {}
                            yield StreamEvent(type="usage", prompt_tokens=u.get("input_tokens", 0), completion_tokens=0)
                        elif kind == "content_block_delta" and (obj.get("delta") or {}).get("type") == "text_delta":
                            yield StreamEvent(type="delta", text=obj["delta"].get("text", ""))
                        elif kind == "message_delta":
                            u = obj.get("usage") or {}
                            if "output_tokens" in u:
                                yield StreamEvent(type="usage", completion_tokens=u["output_tokens"])
                            if (obj.get("delta") or {}).get("stop_reason"):
                                yield StreamEvent(type="finish", finish_reason=obj["delta"]["stop_reason"])
                        elif kind == "error":
                            raise GatewayError(502, "upstream_error", f"Anthropic stream error: {(obj.get('error') or {}).get('message', 'unknown')}"[:500])
            except httpx.RequestError as exc:
                raise GatewayError(502, "upstream_unreachable", f"Network unreachable: {exc}")
