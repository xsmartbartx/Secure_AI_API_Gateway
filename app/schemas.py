from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ChatMessage(BaseModel):
    role: str = Field(..., description="The context producer role: system, user, assistant")
    content: str = Field(..., description="The textual body content of the payload turn")

class UnifiedChatRequest(BaseModel):
    provider: str = Field(..., description="Target model engine runtime (e.g., 'openai', 'anthropic')")
    model: str = Field(..., description="Upstream model instance signature tag (e.g., 'gpt-4o', 'claude-3-5-sonnet')")
    messages: List[ChatMessage] = Field(..., description="Sequential structured chat conversation payload array")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, gt=0)

class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = None

class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0