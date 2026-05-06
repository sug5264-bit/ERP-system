"""Simple in-memory token-bucket rate limiter.

Keyed by (auth identity || client IP). For multi-process production use Redis.
"""
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

SKIP_PREFIXES = ("/api/health", "/api/auth/login", "/api/auth/oauth", "/docs", "/openapi.json")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, default_per_minute: int = 120):
        super().__init__(app)
        self.default = default_per_minute
        self._hits: dict[str, deque[float]] = {}

    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled:
            return await call_next(request)
        if any(request.url.path.startswith(p) for p in SKIP_PREFIXES):
            return await call_next(request)

        identity = request.headers.get("X-API-Key") or request.headers.get(
            "authorization", ""
        ) or (request.client.host if request.client else "anon")
        now = time.monotonic()
        window = now - 60.0

        bucket = self._hits.setdefault(identity, deque())
        while bucket and bucket[0] < window:
            bucket.popleft()

        limit = settings.rate_limit_per_minute or self.default
        if len(bucket) >= limit:
            retry_after = int(60 - (now - bucket[0])) + 1
            return JSONResponse(
                {"detail": "Rate limit exceeded", "retry_after": retry_after},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
        return await call_next(request)
