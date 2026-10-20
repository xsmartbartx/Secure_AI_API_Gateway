import asyncio
import uuid

from app.adapters.base import BaseProviderAdapter
from app.config import settings
from app.schemas import ChatChoice, ChatMessage, StreamEvent, UnifiedChatRequest, UnifiedChatResponse, UsageInfo


class MockAdapter(BaseProviderAdapter):
    """Dev-only upstream. Echoes the last user turn so the whole pipeline can be exercised offline."""

    name = "mock"

    async def execute_chat(self, request: UnifiedChatRequest, credential: str | None = None) -> UnifiedChatResponse:
        last = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
        text = f"[mock] {last[:200]}"
        p = sum(len(m.content) for m in request.messages) // 4 + 1
        c = len(text) // 4 + 1
        return UnifiedChatResponse(
            id=f"mock_{uuid.uuid4().hex[:12]}", provider="mock", model=request.model or "mock-1",
            choices=[ChatChoice(index=0, message=ChatMessage(role="assistant", content=text), finish_reason="stop")],
            usage=UsageInfo(prompt_tokens=p, completion_tokens=c, total_tokens=p + c),
        )

    async def stream_chat(self, request: UnifiedChatRequest, credential: str | None = None):
        full = await self.execute_chat(request)
        text = full.choices[0].message.content
        for i, word in enumerate(text.split(" ")):
            await asyncio.sleep(settings.MOCK_STREAM_DELAY_MS / 1000)
            yield StreamEvent(type="delta", text=(word if i == 0 else " " + word))
        yield StreamEvent(type="usage", prompt_tokens=full.usage.prompt_tokens, completion_tokens=full.usage.completion_tokens)
        yield StreamEvent(type="finish", finish_reason="stop")
