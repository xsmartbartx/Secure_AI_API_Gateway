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