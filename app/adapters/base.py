from abc import ABC, abstractmethod
from app.schemas import UnifiedChatRequest, UnifiedChatResponse

class BaseProviderAdapter(ABC):
    @abstractmethod
    async def execute_chat(self, request: UnifiedChatRequest) -> UnifiedChatResponse:
        """Translates schema structures and proxies network execution requests upstream."""
        pass