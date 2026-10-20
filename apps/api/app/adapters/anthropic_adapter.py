import httpx

from app.adapters.base import BaseProviderAdapter
from app.adapters.sse import check_stream_status, raise_for_status, sse_json
from app.config import settings
from app.errors import GatewayError
from app.schemas import ChatChoice, ChatMessage, StreamEvent, UnifiedChatRequest, UnifiedChatResponse, UsageInfo

NOT_CONFIGURED = "Anthropic upstream provider credentials missing from Gateway. Add your own key under Providers."


def _auth() -> GatewayError:
    return GatewayError(502, "provider_auth_failed", "Anthropic rejected the API key. Check it under Providers.")


def _events(obj: dict) -> list[StreamEvent]:
    """The unified events for one Anthropic stream event. Raises when the provider reports an error in-band."""
    kind = obj.get("type")
    if kind == "message_start":
        usage = (obj.get("message") or {}).get("usage") or {}
        return [StreamEvent(type="usage", prompt_tokens=usage.get("input_tokens", 0), completion_tokens=0)]
    if kind == "content_block_delta" and (obj.get("delta") or {}).get("type") == "text_delta":
        return [StreamEvent(type="delta", text=obj["delta"].get("text", ""))]
    if kind == "message_delta":
        out = []
        usage = obj.get("usage") or {}
        if "output_tokens" in usage:
            out.append(StreamEvent(type="usage", completion_tokens=usage["output_tokens"]))
        stop = (obj.get("delta") or {}).get("stop_reason")
        if stop:
            out.append(StreamEvent(type="finish", finish_reason=stop))
        return out
    if kind == "error":
        message = (obj.get("error") or {}).get("message", "unknown")
        raise GatewayError(502, "upstream_error", f"Anthropic stream error: {message}"[:500])
    return []


class AnthropicAdapter(BaseProviderAdapter):
    name = "anthropic"

    def __init__(self):
        self.url = "https://api.anthropic.com/v1/messages"

    def _headers(self, credential: str | None) -> dict:
        api_key = credential or settings.ANTHROPIC_API_KEY
        if not api_key:
            raise GatewayError(502, "upstream_not_configured", NOT_CONFIGURED)
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}

    @staticmethod
    def _payload(request: UnifiedChatRequest, stream: bool) -> dict:
        """Anthropic takes the system prompt separately from the conversation."""
        system = next((m.content for m in reversed(request.messages) if m.role == "system"), None)
        payload = {"model": request.model, "messages": [{"role": m.role, "content": m.content} for m in request.messages if m.role != "system"],
                   "max_tokens": request.max_tokens or 1024, "temperature": request.temperature}
        if system:
            payload["system"] = system
        if stream:
            payload["stream"] = True
        return payload

    async def execute_chat(self, request: UnifiedChatRequest, credential: str | None = None) -> UnifiedChatResponse:
        headers, payload = self._headers(credential), self._payload(request, stream=False)
        async with httpx.AsyncClient(transport=self.transport) as client:
            try:
                response = await client.post(self.url, json=payload, headers=headers, timeout=60.0)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise raise_for_status(exc, "Anthropic", _auth) from None
            except httpx.RequestError as exc:
                raise GatewayError(502, "upstream_unreachable", f"Network unreachable: {exc}") from None

        data = response.json()
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        usage = data.get("usage", {})
        prompt, completion = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        return UnifiedChatResponse(
            id=data.get("id", "unk"), provider="anthropic", model=data.get("model", request.model),
            choices=[ChatChoice(index=0, message=ChatMessage(role="assistant", content=text), finish_reason=data.get("stop_reason"))],
            usage=UsageInfo(prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion))

    async def stream_chat(self, request: UnifiedChatRequest, credential: str | None = None):
        headers, payload = self._headers(credential), self._payload(request, stream=True)
        async with httpx.AsyncClient(transport=self.transport) as client:
            try:
                async with client.stream("POST", self.url, json=payload, headers=headers, timeout=httpx.Timeout(60.0, read=120.0)) as r:
                    await check_stream_status(r, "Anthropic", _auth)
                    async for obj in sse_json(r):
                        for event in _events(obj):
                            yield event
            except httpx.RequestError as exc:
                raise GatewayError(502, "upstream_unreachable", f"Network unreachable: {exc}") from None
