"""Enforce domain roles even when requests go directly through nginx to FastAPI."""
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.database import get_database
from app.services.domain_access_service import allow_path


class DomainAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # The access probe returns no application data; it checks its own host.
        # Health is needed by the internal container health check.
        if request.url.path in ('/domain-access', '/health'):
            return await call_next(request)
        try:
            allowed = await allow_path(get_database(), request.headers.get('host', ''), request.url.path)
        except Exception:
            logging.exception('Domain access lookup failed')
            return Response(status_code=503, headers={'Cache-Control': 'no-store'})
        if not allowed:
            return Response(status_code=404, headers={'Cache-Control': 'no-store'})
        return await call_next(request)
