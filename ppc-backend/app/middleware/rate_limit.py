import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.core.constants import MAX_REQUESTS_PER_IP_PER_MINUTE
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP-based rate limiting middleware using Redis."""

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for static files and health checks
        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        try:
            from app.cache.redis_client import get_redis
            from app.core.constants import REDIS_REQUEST_RATE_PREFIX
            redis = get_redis()
            if redis:
                key = f"{REDIS_REQUEST_RATE_PREFIX}{client_ip}"
                count = await redis.incr(key)
                if count == 1:
                    await redis.expire(key, 60)
                if count > MAX_REQUESTS_PER_IP_PER_MINUTE:
                    return JSONResponse(
                        status_code=429,
                        content={"success": False, "error": "Too many requests"},
                    )
        except Exception as e:
            logger.warning(f"Rate limit check error: {e}")

        return await call_next(request)
