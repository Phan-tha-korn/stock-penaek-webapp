from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from server.config.settings import settings


class EnforceHTTPSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if settings.enforce_https:
            proto = request.headers.get("x-forwarded-proto") or request.url.scheme
            if proto != "https":
                return JSONResponse({"detail": "https_required"}, status_code=400)
        return await call_next(request)

