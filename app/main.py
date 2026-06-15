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

@app.get("/health")
async def validation_health_check():
    return {"status": "operational"}

@app.post("/v1/chat/completions", response_model=UnifiedChatResponse)
async def route_unified_chat_request(request: UnifiedChatRequest):
    target_provider = request.provider.lower()
    
    if target_provider not in provider_registry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider runtime reference selection '{request.provider}' unrecognized. Support handles: {list(provider_registry.keys())}"
        )
    
    selected_adapter = provider_registry[target_provider]
    execution_result = await selected_adapter.execute_chat(request)
    return execution_result