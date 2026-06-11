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