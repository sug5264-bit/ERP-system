import json

from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.db import SessionLocal
from app.core.security import decode_token

WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

# Skip audit-body capture entirely on these paths. Health/docs are noise; the
# upload endpoints would otherwise force the whole file into memory twice
# (once for body capture, once for the re-injected receive stream).
SKIP_PREFIXES = (
    "/api/auth/login",
    "/api/audit",
    "/docs",
    "/openapi.json",
    "/metrics",
)

# These paths still get an audit row, but with the request body NOT captured.
# Multipart uploads can be hundreds of MB; we only want method/path/status.
SKIP_BODY_PREFIXES = (
    "/api/attachments",
    "/api/ocr",
    "/api/admin/restore",
    "/api/admin/import",
)

# Hard cap so a malformed/streaming JSON body can't OOM the audit logger.
MAX_BODY_BYTES = 64 * 1024  # 64 KB — anything larger is likely a binary/upload
MAX_PAYLOAD = 4000


class AuditMiddleware(BaseHTTPMiddleware):
    """Persist a record of every write request for the admin audit log."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_write = request.method in WRITE_METHODS
        is_audited = is_write and not any(path.startswith(p) for p in SKIP_PREFIXES)
        capture_body = is_audited and not any(
            path.startswith(p) for p in SKIP_BODY_PREFIXES
        )

        body_bytes = b""
        if capture_body:
            raw = await request.body()
            # Truncate very large bodies — protects the logger from OOM.
            body_bytes = raw[:MAX_BODY_BYTES]

            async def receive(_full=raw):
                return {"type": "http.request", "body": _full, "more_body": False}

            request = Request(request.scope, receive)

        response: Response = await call_next(request)

        if is_audited:
            self._log(request, response, body_bytes, captured=capture_body)

        return response

    def _log(self, request: Request, response: Response, body: bytes, *, captured: bool) -> None:
        from app.modules.audit.models import AuditLog
        from app.modules.auth.models import User

        user_id, user_email = None, None
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                payload = decode_token(auth.split(" ", 1)[1])
                user_id = int(payload.get("sub", 0)) or None
            except (JWTError, ValueError):
                pass

        if captured:
            snippet = (
                body.decode("utf-8", errors="replace")[:MAX_PAYLOAD] if body else None
            )
            if snippet and "password" in snippet.lower():
                try:
                    parsed = json.loads(snippet)
                    if isinstance(parsed, dict) and "password" in parsed:
                        parsed["password"] = "***"
                        snippet = json.dumps(parsed)
                except json.JSONDecodeError:
                    pass
        else:
            snippet = "(body skipped — large/binary payload)"

        db = SessionLocal()
        try:
            if user_id:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    user_email = user.email
            db.add(
                AuditLog(
                    user_id=user_id,
                    user_email=user_email,
                    method=request.method,
                    path=str(request.url.path),
                    status_code=response.status_code,
                    ip=request.client.host if request.client else None,
                    payload=snippet,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            import logging

            logging.getLogger("erp.audit").exception(
                "audit log write failed for %s %s", request.method, request.url.path
            )
        finally:
            db.close()
