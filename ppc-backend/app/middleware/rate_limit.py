"""
Rate limit middleware — high-performance rewrite.

Uses a Redis Lua script to combine INCR + EXPIRE into a single atomic
round-trip, halving Redis latency compared to two separate calls.
Skips static assets entirely.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.core.constants import MAX_REQUESTS_PER_IP_PER_MINUTE
import logging

logger = logging.getLogger(__name__)

# Lua script: INCR + conditional EXPIRE in one round-trip
_LUA_INCR_EXPIRE = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""

# Paths that are never rate-limited
_NO_LIMIT_PATHS = frozenset([
    "/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico",
])
_NO_LIMIT_PREFIXES = ("/_next/static/", "/uploads/")

_RATE_WINDOW = 60   # seconds
_TOO_MANY = {"success": False, "error": "Too many requests"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP-based rate limiting. One atomic Redis round-trip per non-static request."""

    def __init__(self, app):
        super().__init__(app)
        self._script_sha: str | None = None   # cached EVALSHA

    async def _get_script_sha(self, redis) -> str | None:
        """Load the Lua script once and cache the SHA."""
        if self._script_sha is None:
            try:
                self._script_sha = await redis.script_load(_LUA_INCR_EXPIRE)
            except Exception as e:
                logger.warning("Could not load Lua rate-limit script: %s", e)
        return self._script_sha

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Fast-path: skip rate-limiting for infra / static paths
        if path in _NO_LIMIT_PATHS:
            return await call_next(request)
        for prefix in _NO_LIMIT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        try:
            from app.cache.redis_client import get_redis
            from app.core.constants import REDIS_REQUEST_RATE_PREFIX
            redis = get_redis()
            if redis:
                client_ip = request.client.host if request.client else "unknown"
                key = f"{REDIS_REQUEST_RATE_PREFIX}{client_ip}"

                sha = await self._get_script_sha(redis)
                if sha:
                    count = await redis.evalsha(sha, 1, key, _RATE_WINDOW)
                else:
                    # Fallback: two round-trips (script_load failed)
                    count = await redis.incr(key)
                    if count == 1:
                        await redis.expire(key, _RATE_WINDOW)

                if count > MAX_REQUESTS_PER_IP_PER_MINUTE:
                    return JSONResponse(status_code=429, content=_TOO_MANY)
        except Exception as e:
            logger.warning("Rate limit check error: %s", e)

        return await call_next(request)
