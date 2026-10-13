import httpx
from app.errors import GatewayError
from app.adapters.base import BaseProviderAdapter
from app.schemas import UnifiedChatRequest, UnifiedChatResponse, ChatChoice, ChatMessage, UsageInfo
from app.config import settings

class AnthropicAdapter(BaseProviderAdapter):
    name = 'anthropic'

    def __init__(self):
        self.url = "https://api.anthropic.com/v1/messages"

    async def execute_chat(self, request: UnifiedChatRequest) -> UnifiedChatResponse:
        if not settings.ANTHROPIC_API_KEY:
            raise GatewayError(
                502, 'upstream_not_configured', "Anthropic upstream provider credentials missing from Gateway.")

        headers = {
            "x-api-key": settings.ANTHROPIC_API_KEY,
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

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.url, json=payload, headers=headers, timeout=60.0)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
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