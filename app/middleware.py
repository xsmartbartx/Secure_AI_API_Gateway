import time
import logging
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
from app.config import settings

# Setup isolated explicit gateway logging architecture
logger = logging.getLogger("gateway_telemetry")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

class InMemorySlidingRateLimiter:
    def __init__(self, limit: int):
        self.limit = limit
        self.history = defaultdict(list)

    def verify_and_consume(self, identification_key: str) -> bool:
        now = time.time()
        # Filter sliding track updates matching last 60 seconds
        self.history[identification_key] = [t for t in self.history[identification_key] if now - t < 60]
        if len(self.history[identification_key]) < self.limit:
            self.history[identification_key].append(now)
            return True
        return False

rate_limiter = InMemorySlidingRateLimiter(settings.RATE_LIMIT_PER_MINUTE)

class GatewaySecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Expose baseline discovery metrics and automatic OpenAPI specification documentation UI
        if request.url.path in ["/docs", "/openapi.json", "/health", "/redoc"]:
            return await call_next(request)
        
        # 1. Verification of Client-Facing Access Token Credentials
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return Response(status_code=status.HTTP_401_UNAUTHORIZED, content="Malformed/Missing Gateway Bearer authorization token.")