"""
Security Middleware — high-performance rewrite.

All patterns, strings and header values are computed once at module load,
not on every request. Middleware classes are kept thin so async overhead
is minimal at 4000-5000 req/s.
"""

import re
import uuid
import hmac
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from fastapi import status

logger = logging.getLogger(__name__)

# ─── Pre-compiled patterns (module-level, computed ONCE) ──────────────────────
_SQL_PATTERN = re.compile(
    r"union\s+select|drop\s+table|insert\s+into|delete\s+from|"
    r"update\s+.*\s+set|exec\(|execute\(|'\s*or\s*'.*'\s*=\s*'",
    re.IGNORECASE,
)
_PATH_TRAVERSAL = re.compile(r"\.\.[/\\]|%2e%2e[%2f%5c]", re.IGNORECASE)

# ─── Pre-built header strings (computed ONCE) ──────────────────────────────────
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
_PERMISSIONS = (
    "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
)
_HSTS = "max-age=31536000; includeSubDomains"

# Static headers added to every response
_STATIC_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": _CSP,
    "Permissions-Policy": _PERMISSIONS,
}

# Paths that skip security middleware entirely
_SKIP_PATHS = frozenset(["/health", "/docs", "/redoc", "/openapi.json"])
_STATIC_PREFIXES = ("/_next/static/", "/uploads/")

# Auth paths for audit logging
_AUTH_PATH_PART = "/auth/"
_ADMIN_PATH_PART = "/admin/"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses. Pre-built headers, no per-request allocation."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        headers = response.headers
        for k, v in _STATIC_HEADERS.items():
            headers[k] = v
        if request.url.scheme == "https":
            headers["Strict-Transport-Security"] = _HSTS
        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Validate requests for common attacks. Uses pre-compiled patterns."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip static assets entirely — no validation needed
        for prefix in _STATIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Path traversal check
        if _PATH_TRAVERSAL.search(path):
            logger.warning("Path traversal attempt: %s", path)
            return JSONResponse(status_code=400, content={"detail": "Invalid request"})

        # SQL injection in query string (pre-compiled pattern)
        qs = request.url.query
        if qs and _SQL_PATTERN.search(qs):
            logger.warning("SQL injection attempt in query: %.120s", qs)
            return JSONResponse(status_code=400, content={"detail": "Invalid request"})

        # Content-length guard (skip header parsing for most requests)
        cl = request.headers.get("content-length")
        if cl and int(cl) > 10 * 1024 * 1024:
            return JSONResponse(status_code=413, content={"detail": "Request too large"})

        return await call_next(request)


class SecurityAuditMiddleware(BaseHTTPMiddleware):
    """Audit auth and admin operations. Only logs — very low overhead."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_auth = _AUTH_PATH_PART in path
        is_admin_write = (
            _ADMIN_PATH_PART in path
            and request.method in ("POST", "PUT", "DELETE", "PATCH")
        )

        if is_auth:
            logger.info(
                "Auth attempt: %s %s from %s",
                request.method, path,
                request.client.host if request.client else "unknown",
            )

        response = await call_next(request)

        if is_auth and response.status_code in (401, 403):
            logger.warning(
                "Failed auth: %s %s status=%d ip=%s",
                request.method, path, response.status_code,
                request.client.host if request.client else "unknown",
            )
        elif is_admin_write:
            logger.info(
                "Admin op: %s %s status=%d",
                request.method, path, response.status_code,
            )

        return response


class SessionSecurityMiddleware(BaseHTTPMiddleware):
    """Session cookie hardening. Skips static assets and health check."""

    async def dispatch(self, request: Request, call_next):
        # Skip static assets — they never set cookies
        path = request.url.path
        if path in _SKIP_PATHS:
            return await call_next(request)

        # Validate existing session cookie format
        session_id = request.cookies.get("session_id")
        if session_id and (len(session_id) < 32 or not session_id.isalnum()):
            logger.warning("Invalid session ID format")
            resp = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid session"},
            )
            resp.delete_cookie("session_id")
            return resp

        response = await call_next(request)

        # Harden Set-Cookie headers
        try:
            if "Set-Cookie" in response.headers:
                cookies = response.headers.getlist("Set-Cookie")
                new_cookies = []
                is_https = request.url.scheme == "https"
                for cookie in cookies:
                    is_tab_bridge = cookie.startswith("mpa_tab_ok=")
                    if "HttpOnly" not in cookie and not is_tab_bridge:
                        cookie += "; HttpOnly"
                    if "SameSite" not in cookie:
                        cookie += "; SameSite=Lax"
                    if is_https and "Secure" not in cookie:
                        cookie += "; Secure"
                    new_cookies.append(cookie)
                del response.headers["Set-Cookie"]
                for cookie in new_cookies:
                    response.headers.append("Set-Cookie", cookie)
        except Exception as e:
            logger.warning("Cookie hardening skipped: %s", e)

        return response


class APISecurityMiddleware(BaseHTTPMiddleware):
    """API security checks. UUID is generated only once per request (not twice)."""

    async def dispatch(self, request: Request, call_next):
        # API key format validation (only if key present — rare)
        api_key = request.headers.get("X-API-Key")
        if api_key and len(api_key) < 32:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid API key"},
            )

        # Assign request ID once
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ─── Helper utilities (unchanged API) ─────────────────────────────────────────

def validate_object_id(obj_id: str) -> bool:
    return bool(re.match(r'^[a-f0-9]{24}$', obj_id, re.IGNORECASE))


def check_resource_ownership(user_id: str, resource_user_id: str, is_admin: bool = False) -> bool:
    if is_admin:
        return True
    return str(user_id) == str(resource_user_id)


class RateLimitExceeded(Exception):
    pass


async def check_endpoint_rate_limit(request: Request, redis, endpoint: str, limit: int, window_seconds: int):
    if not redis:
        return
    client_ip = request.client.host if request.client else "unknown"
    key = f"rate_limit:{endpoint}:{client_ip}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
        if count > limit:
            raise RateLimitExceeded(f"Rate limit exceeded: {limit} requests per {window_seconds}s")
    except RateLimitExceeded:
        raise
    except Exception as e:
        logger.error("Rate limit check error: %s", e)


def sanitize_error_message(error: Exception) -> str:
    error_str = str(error)
    error_str = re.sub(r'/[a-zA-Z0-9_/.-]+\.py', '[file]', error_str)
    error_str = re.sub(r"ObjectId\([\"']?[a-f0-9]{24}[\"']?\)", '[id]', error_str)
    if "duplicate key error" in error_str.lower():
        return "Resource already exists"
    if "cast to objectid failed" in error_str.lower():
        return "Invalid ID format"
    if len(error_str) > 200:
        return "An error occurred processing your request"
    return error_str


def check_csrf_token(request: Request, token: str) -> bool:
    header_token = request.headers.get("X-CSRF-Token")
    if not header_token:
        return False
    return hmac.compare_digest(token, header_token)
