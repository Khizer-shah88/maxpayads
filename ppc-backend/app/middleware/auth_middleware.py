from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.security import decode_token
import logging

logger = logging.getLogger(__name__)

# Paths that don't require authentication
PUBLIC_PATHS = [
    "/health",
    "/auth/login",
    "/auth/register",
    "/click",
    "/ad.js",
    "/docs",
    "/openapi.json",
    "/redoc",
]


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for public paths
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = decode_token(token)
            if payload:
                request.state.user_id = payload.get("sub")
                request.state.user_role = payload.get("role", "publisher")

        return await call_next(request)
