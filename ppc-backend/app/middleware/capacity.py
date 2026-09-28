"""Bound application work per worker; keep probes responsive under overload."""
from starlette.responses import JSONResponse
from app.config import settings


class CapacityMiddleware:
    def __init__(self, app):
        self.app = app
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] in ('/health', '/domain-access'):
            return await self.app(scope, receive, send)
        if self.active >= settings.API_MAX_INFLIGHT:
            return await JSONResponse(
                {'success': False, 'error': 'Server busy; please retry'}, status_code=503,
                headers={'Retry-After': '1', 'Cache-Control': 'no-store'},
            )(scope, receive, send)
        # No await between check and increment; this counter is event-loop local.
        self.active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.active -= 1
