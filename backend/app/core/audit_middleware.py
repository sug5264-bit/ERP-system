import json

from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.db import SessionLocal
from app.core.security import decode_token

WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
SKIP_PREFIXES = ("/api/auth/login", "/api/audit", "/docs", "/openapi.json")
MAX_PAYLOAD = 4000


class AuditMiddleware(BaseHTTPMiddleware):
    """Persist a record of every write request for the admin audit log."""

    async def dispatch(self, request: Request, call_next):
        body_bytes = b""
        if request.method in WRITE_METHODS and not any(
            request.url.path.startswith(p) for p in SKIP_PREFIXES
        ):
            body_bytes = await request.body()

            # Re-inject the body so downstream handlers can still read it.
            async def receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            request = Request(request.scope, receive)

        response: Response = await call_next(request)

        if request.method in WRITE_METHODS and not any(
            request.url.path.startswith(p) for p in SKIP_PREFIXES
        ):
            self._log(request, response, body_bytes)

        return response

    def _log(self, request: Request, response: Response, body: bytes) -> None:
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

        snippet = body.decode("utf-8", errors="replace")[:MAX_PAYLOAD] if body else None
        # Mask passwords from logged payloads.
        if snippet and "password" in snippet.lower():
            try:
                parsed = json.loads(snippet)
                if isinstance(parsed, dict) and "password" in parsed:
                    parsed["password"] = "***"
                    snippet = json.dumps(parsed)
            except json.JSONDecodeError:
                pass

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
        finally:
            db.close()
