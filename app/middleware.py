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
        
        client_key = auth_header.split(" ")[1]
        if client_key not in settings.valid_keys:
            return Response(status_code=status.HTTP_403_FORBIDDEN, content="Forbidden: Provided Gateway API access key is rejected.")

        # 2. Key-Identified Operational Rate Control Boundary Check
        if not rate_limiter.verify_and_consume(client_key):
            return Response(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content="Rate limit threshold violation. Slow down requests.")
        
        # 3. Telemetry Log Capture Tracking Round-Trip Runtime Performance
        start_time = time.time()
        logger.info(f"Route Call: path={request.url.path} method={request.method} key_id=...{client_key[-6:]}")
        
        try:
            response = await call_next(request)
            execution_delay = time.time() - start_time
            logger.info(f"Route Done: status={response.status_code} latency={execution_delay:.4f}s")
            return response
        except Exception as error:
            execution_delay = time.time() - start_time
            logger.error(f"Route Failure: error={str(error)} latency={execution_delay:.4f}s")
            return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content="Gateway execution anomaly.")