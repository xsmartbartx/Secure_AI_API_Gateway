from abc import ABC, abstractmethod
from typing import AsyncIterator

from app.schemas import StreamEvent, UnifiedChatRequest, UnifiedChatResponse


class BaseProviderAdapter(ABC):
    name: str
    transport = None  # tests inject an httpx transport

    @abstractmethod
    async def execute_chat(self, request: UnifiedChatRequest) -> UnifiedChatResponse:
        """Translate the unified request, call the upstream, return a unified response."""

    @abstractmethod
    def stream_chat(self, request: UnifiedChatRequest) -> AsyncIterator[StreamEvent]:
        """Same, but yield StreamEvents as the upstream produces them. Raises GatewayError before the first
        event when the upstream refuses the request, so the caller can still answer with a normal HTTP error."""
