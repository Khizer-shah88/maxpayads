"""Per-visitor limits. Internal authorization probes never consume user quotas."""
import hashlib
import logging
import time

from redis.exceptions import NoScriptError
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.core.constants import REDIS_REQUEST_RATE_PREFIX
from app.utils.proxy_ip import client_ip

logger = logging.getLogger(__name__)
_LUA_INCR_EXPIRE = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""
_SCRIPT_SHA = hashlib.sha1(_LUA_INCR_EXPIRE.encode()).hexdigest()
_NO_LIMIT_PATHS = frozenset(['/domain-access', '/health', '/docs', '/redoc', '/openapi.json', '/favicon.ico'])
_NO_LIMIT_PREFIXES = ('/_next/', '/uploads/')


class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app
        self._last_error = float('-inf')

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] in _NO_LIMIT_PATHS or scope['path'].startswith(_NO_LIMIT_PREFIXES):
            return await self.app(scope, receive, send)
        try:
            from app.cache.redis_client import get_redis
            redis = get_redis()
            if redis:
                key = f'{REDIS_REQUEST_RATE_PREFIX}{client_ip(Request(scope))}'
                try:
                    count = await redis.evalsha(_SCRIPT_SHA, 1, key, 60)
                except NoScriptError:
                    # Handles cold start and SCRIPT FLUSH without disabling limits.
                    count = await redis.eval(_LUA_INCR_EXPIRE, 1, key, 60)
                if count > settings.REQUESTS_PER_IP_PER_MINUTE:
                    response = JSONResponse(
                        {'success': False, 'error': 'Too many requests'}, status_code=429,
                        headers={'Retry-After': '60', 'Cache-Control': 'no-store'},
                    )
                    return await response(scope, receive, send)
        except Exception:
            now = time.monotonic()
            if now - self._last_error > 30:
                logger.exception('Rate limit store unavailable')
                self._last_error = now
        await self.app(scope, receive, send)
