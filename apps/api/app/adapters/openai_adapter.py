import httpx

from app.adapters.base import BaseProviderAdapter
from app.adapters.sse import check_stream_status, raise_for_status, sse_json
from app.config import settings
from app.errors import GatewayError
from app.schemas import ChatChoice, ChatMessage, StreamEvent, UnifiedChatRequest, UnifiedChatResponse, UsageInfo

NOT_CONFIGURED = "OpenAI upstream provider credentials missing from Gateway. Add your own key under Providers."


def _auth() -> GatewayError:
    return GatewayError(502, "provider_auth_failed", "OpenAI rejected the API key. Check it under Providers.")


def _events(obj: dict) -> list[StreamEvent]:
    """The unified events for one OpenAI stream chunk."""
    out = []
    for choice in obj.get("choices") or []:
        text = (choice.get("delta") or {}).get("content")
        if text:
            out.append(StreamEvent(type="delta", text=text))
        if choice.get("finish_reason"):
            out.append(StreamEvent(type="finish", finish_reason=choice["finish_reason"]))
    usage = obj.get("usage")
    if usage:
        out.append(StreamEvent(type="usage", prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0)))
    return out


class OpenAIAdapter(BaseProviderAdapter):
    name = "openai"

    def __init__(self):
        self.url = "https://api.openai.com/v1/chat/completions"

    def _headers(self, credential: str | None) -> dict:
        api_key = credential or settings.OPENAI_API_KEY
        if not api_key:
            raise GatewayError(502, "upstream_not_configured", NOT_CONFIGURED)
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _payload(request: UnifiedChatRequest, stream: bool) -> dict:
        payload = {"model": request.model, "messages": [m.model_dump() for m in request.messages], "temperature": request.temperature}
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if stream:
            payload.update(stream=True, stream_options={"include_usage": True})
        return payload

    async def execute_chat(self, request: UnifiedChatRequest, credential: str | None = None) -> UnifiedChatResponse:
        headers, payload = self._headers(credential), self._payload(request, stream=False)
        async with httpx.AsyncClient(transport=self.transport) as client:
            try:
                response = await client.post(self.url, json=payload, headers=headers, timeout=60.0)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise raise_for_status(exc, "OpenAI", _auth) from None
            except httpx.RequestError as exc:
                raise GatewayError(502, "upstream_unreachable", f"Network unreachable: {exc}") from None

        data = response.json()
        usage = data.get("usage", {})
        return UnifiedChatResponse(
            id=data.get("id", "unk"), provider="openai", model=data.get("model", request.model),
            choices=[ChatChoice(index=c.get("index", 0),
                                message=ChatMessage(role=c.get("message", {}).get("role", "assistant"), content=c.get("message", {}).get("content", "")),
                                finish_reason=c.get("finish_reason")) for c in data.get("choices", [])],
            usage=UsageInfo(prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0),
                            total_tokens=usage.get("total_tokens", 0)))

    async def stream_chat(self, request: UnifiedChatRequest, credential: str | None = None):
        headers, payload = self._headers(credential), self._payload(request, stream=True)
        async with httpx.AsyncClient(transport=self.transport) as client:
            try:
                async with client.stream("POST", self.url, json=payload, headers=headers, timeout=httpx.Timeout(60.0, read=120.0)) as r:
                    await check_stream_status(r, "OpenAI", _auth)
                    async for obj in sse_json(r):
                        for event in _events(obj):
                            yield event
            except httpx.RequestError as exc:
                raise GatewayError(502, "upstream_unreachable", f"Network unreachable: {exc}") from None
