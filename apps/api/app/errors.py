from fastapi import Request
from fastapi.responses import JSONResponse


class GatewayError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


def envelope(status: int, code: str, message: str, request_id: str = "", headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers=headers,
    )


async def gateway_error_handler(request: Request, exc: GatewayError):
    return envelope(exc.status, exc.code, exc.message, getattr(request.state, "request_id", ""), exc.headers)
