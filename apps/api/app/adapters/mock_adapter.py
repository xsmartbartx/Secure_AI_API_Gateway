import uuid

from app.adapters.base import BaseProviderAdapter
from app.schemas import ChatChoice, ChatMessage, UnifiedChatRequest, UnifiedChatResponse, UsageInfo


class MockAdapter(BaseProviderAdapter):
    """Dev-only upstream. Echoes the last user turn so the whole pipeline can be exercised offline."""

    name = "mock"

    async def execute_chat(self, request: UnifiedChatRequest) -> UnifiedChatResponse:
        last = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
        text = f"[mock] {last[:200]}"
        p = sum(len(m.content) for m in request.messages) // 4 + 1
        c = len(text) // 4 + 1
        return UnifiedChatResponse(
            id=f"mock_{uuid.uuid4().hex[:12]}", provider="mock", model=request.model or "mock-1",
            choices=[ChatChoice(index=0, message=ChatMessage(role="assistant", content=text), finish_reason="stop")],
            usage=UsageInfo(prompt_tokens=p, completion_tokens=c, total_tokens=p + c),
        )
