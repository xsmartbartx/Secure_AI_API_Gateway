from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ChatMessage(BaseModel):
    role: str = Field(..., description="The context producer role: system, user, assistant")
    content: str = Field(..., description="The textual body content of the payload turn")