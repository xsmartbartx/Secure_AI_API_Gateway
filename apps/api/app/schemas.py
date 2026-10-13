from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., max_length=200_000)


class UnifiedChatRequest(BaseModel):
    model: str | None = None
    provider: str | None = None
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=200)
    temperature: float | None = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, gt=0, le=64_000)
    stream: bool = False


class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None = None


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class UnifiedChatResponse(BaseModel):
    id: str
    provider: str
    model: str
    choices: list[ChatChoice]
    usage: UsageInfo
