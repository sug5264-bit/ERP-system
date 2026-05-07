"""Adds standard security headers to every response.

Note: when running behind a reverse proxy (nginx/Cloudflare), prefer setting
these at the proxy level so they apply to static files too.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )
        # API responses don't need a CSP, but if the same host serves the SPA
        # this is a sensible baseline. Adjust for your deployment.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
            "connect-src 'self' ws: wss: https:; "
            "frame-ancestors 'none'; base-uri 'self'",
        )
        return response
