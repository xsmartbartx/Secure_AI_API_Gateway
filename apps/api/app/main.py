import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.errors import GatewayError, envelope, gateway_error_handler
from app.routers import billing, control, data


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.ENV == "prod":  # prod uses Alembic migrations; refuse unsafe config
        if not settings.AUTH_JWKS_URL or not settings.AUTH_ISSUER:
            raise RuntimeError("ENV=prod requires AUTH_JWKS_URL and AUTH_ISSUER")
        if not settings.REDIS_URL:
            raise RuntimeError("ENV=prod requires REDIS_URL for shared rate limits")
    else:
        await init_db()
    yield


app = FastAPI(title="NEXORA Gateway API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["authorization", "content-type", "x-dev-org", "x-dev-user", "x-dev-role"],
    expose_headers=["x-nexora-request-id", "retry-after"],
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
