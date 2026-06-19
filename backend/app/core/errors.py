"""Standard error envelope + global exception handlers.

All error responses share the shape:
    {"error": {"code": "ERROR_CODE", "message": "Human message", "request_id": "..."}}

Add ERPError subclasses for business errors that need stable codes.
"""
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ERPError(Exception):
    """Base for business errors. Code lets clients branch on error type."""

    code: str = "ERROR"
    status_code: int = 400

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        super().__init__(message)


def _envelope(request: Request, code: str, message: str, status_code: int) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": rid}},
    )


def _http_code_to_error_code(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHENTICATED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        415: "UNSUPPORTED_MEDIA_TYPE",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        503: "UNAVAILABLE",
    }.get(status_code, f"HTTP_{status_code}")


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ERPError)
    async def _erp_error(request: Request, exc: ERPError):
        return _envelope(request, exc.code, exc.message, exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        # Preserve the existing detail field so untouched clients still work,
        # but layer the new envelope on top.
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return _envelope(request, _http_code_to_error_code(exc.status_code), detail, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        rid = getattr(request.state, "request_id", None)
        # Pydantic v2 errors()는 ctx에 raw exception 객체를 넣어두는데
        # 그대로면 JSON 직렬화 실패. str()로 평면화.
        safe_fields = []
        first_msg = "Request validation failed"
        for e in exc.errors():
            ctx = e.get("ctx") or {}
            safe_ctx = {k: str(v) for k, v in ctx.items()}
            safe_fields.append(
                {
                    "loc": list(e.get("loc", [])),
                    "msg": e.get("msg"),
                    "type": e.get("type"),
                    "ctx": safe_ctx,
                }
            )
            # 첫 에러 메시지를 envelope.message로 노출 (한글 검증 메시지 살리기)
            if first_msg == "Request validation failed" and e.get("msg"):
                first_msg = str(e["msg"])
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": first_msg,
                    "request_id": rid,
                    "fields": safe_fields,
                }
            },
        )
