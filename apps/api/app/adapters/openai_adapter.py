import httpx
from app.errors import GatewayError
from app.adapters.base import BaseProviderAdapter
from app.schemas import UnifiedChatRequest, UnifiedChatResponse, ChatChoice, ChatMessage, UsageInfo
from app.config import settings

class OpenAIAdapter(BaseProviderAdapter):
    name = 'openai'

    def __init__(self):
        self.url = "https://api.openai.com/v1/chat/completions"

    async def execute_chat(self, request: UnifiedChatRequest) -> UnifiedChatResponse:
        if not settings.OPENAI_API_KEY:
            raise GatewayError(
                502, 'upstream_not_configured', "OpenAI upstream provider credentials missing from Gateway.")

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": request.model,
            "messages": [msg.model_dump() for msg in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.url, json=payload, headers=headers, timeout=60.0)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
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