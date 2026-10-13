from abc import ABC, abstractmethod

from app.schemas import UnifiedChatRequest, UnifiedChatResponse


class BaseProviderAdapter(ABC):
    name: str

    @abstractmethod
    async def execute_chat(self, request: UnifiedChatRequest) -> UnifiedChatResponse:
        """Translate the unified request, call the upstream, return a unified response."""
