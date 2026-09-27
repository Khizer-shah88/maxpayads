"""Enforce domain roles even when requests go directly through nginx to FastAPI."""
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.database import get_database
from app.services.domain_access_service import allow_path

logger = logging.getLogger(__name__)

# In-process LRU cache: host → (role_or_none, expires_at)
# Avoids a MongoDB round-trip on every single request.
# TTL is short (30s) so domain changes take effect quickly.
_DOMAIN_CACHE: dict = {}
_CACHE_TTL = 30.0   # seconds
_MAX_ENTRIES = 500  # prevent unbounded growth


def _cache_get(host: str):
    entry = _DOMAIN_CACHE.get(host)
    if entry is None:
        return None, False          # miss
    role, expires = entry
    if time.monotonic() > expires:
        _DOMAIN_CACHE.pop(host, None)
        return None, False          # expired
    return role, True               # hit


def _cache_set(host: str, role):
    if len(_DOMAIN_CACHE) >= _MAX_ENTRIES:
        # Evict oldest 20 % to make room
        cutoff = sorted(_DOMAIN_CACHE.values(), key=lambda v: v[1])[
            int(_MAX_ENTRIES * 0.2)
        ][1]
        to_delete = [k for k, v in _DOMAIN_CACHE.items() if v[1] <= cutoff]
        for k in to_delete:
            _DOMAIN_CACHE.pop(k, None)
    _DOMAIN_CACHE[host] = (role, time.monotonic() + _CACHE_TTL)


# Paths that skip domain validation entirely — no DB lookup needed
_SKIP_PATHS = frozenset([
    '/domain-access', '/health', '/docs', '/redoc',
    '/openapi.json', '/favicon.ico',
])
_SKIP_PREFIXES = ('/_next/', '/uploads/', '/api/auth/')


class DomainAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path

        # Fast-path: skip for health/infra endpoints
        if path in _SKIP_PATHS:
            return await call_next(request)
        for prefix in _SKIP_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        host = request.headers.get('host', '')

        # Try cache first — avoid DB hit on every request
        role, hit = _cache_get(host)
        if hit:
            if not role:
                return Response(status_code=404, headers={'Cache-Control': 'no-store'})
            return await call_next(request)

        # Cache miss: ask the DB
        try:
            role = await allow_path(get_database(), host, path)
        except Exception:
            logger.exception('Domain access lookup failed')
            # Don't cache errors — retry on next request
            return Response(status_code=503, headers={'Cache-Control': 'no-store'})

        # Only cache the role (True/False), not the full path check
        # The path check itself is cheap; the DB lookup for the host is expensive
        # Cache whether this host is known at all
        _cache_set(host, role)

        if not role:
            return Response(status_code=404, headers={'Cache-Control': 'no-store'})
        return await call_next(request)
