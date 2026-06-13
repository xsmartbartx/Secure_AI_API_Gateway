from fastapi import FastAPI, HTTPException, status
from app.schemas import UnifiedChatRequest, UnifiedChatResponse
from app.middleware import GatewaySecurityMiddleware
from app.adapters.openai_adapter import OpenAIAdapter
from app.adapters.anthropic_adapter import AnthropicAdapter

app = FastAPI(
    title="Secure AI API Gateway",
    description="Unified request mapping engine and token safety abstraction layer.",
    version="1.0.0"
)
# Wire core security and routing middleware hooks
app.add_middleware(GatewaySecurityMiddleware)

# Initialize functional downstream multi-provider model routing drivers
provider_registry = {
    "openai": OpenAIAdapter(),
    "anthropic": AnthropicAdapter()
}