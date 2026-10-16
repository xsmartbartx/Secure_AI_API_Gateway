import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.retention import retention_loop
from app.errors import GatewayError, envelope, gateway_error_handler
from app.routers import account, billing, control, data, export, providers as provider_routes, team


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def check_production_settings() -> None:
    """The API refuses to start in production with settings that would silently weaken security."""
    if not settings.AUTH_JWKS_URL or not settings.AUTH_ISSUER:
        raise RuntimeError("ENV=prod requires AUTH_JWKS_URL and AUTH_ISSUER")
    if not settings.CREDENTIAL_ENCRYPTION_KEY:
        raise RuntimeError("ENV=prod requires CREDENTIAL_ENCRYPTION_KEY")
    if not settings.REDIS_URL:
        raise RuntimeError("ENV=prod requires REDIS_URL for shared rate limits")
    if settings.STRIPE_SECRET_KEY and not settings.STRIPE_WEBHOOK_SECRET:
        raise RuntimeError("ENV=prod with Stripe enabled requires STRIPE_WEBHOOK_SECRET (an empty secret makes forged webhooks verifiable)")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.ENV == "prod":  # prod uses Alembic migrations; refuse unsafe config
        check_production_settings()
    else:
        await init_db()
    task = asyncio.create_task(retention_loop()) if settings.RETENTION_JOB_ENABLED else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="NEXORA Gateway API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["authorization", "content-type", "x-dev-org", "x-dev-user", "x-dev-role"],
    expose_headers=["x-nexora-request-id", "retry-after", "content-disposition"],
)


@app.middleware("http")
async def request_id(request: Request, call_next):
    request.state.request_id = f"req_{uuid.uuid4().hex[:16]}"
    response = await call_next(request)
    response.headers["x-nexora-request-id"] = request.state.request_id
    return response


app.add_exception_handler(GatewayError, gateway_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    if first.get("type") == "json_invalid":
        return envelope(422, "invalid_request", "Request body is not valid JSON.", request.state.request_id)
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return envelope(422, "invalid_request", f"{loc}: {first.get('msg', 'invalid')}".strip(": "), request.state.request_id)


app.include_router(data.router)
app.include_router(control.router)
app.include_router(billing.router)
app.include_router(account.router)
app.include_router(provider_routes.router)
app.include_router(export.router)
app.include_router(team.router)
