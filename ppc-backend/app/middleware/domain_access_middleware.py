"""Domain policy and lightweight internal authorization, without user throttling."""
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.database import get_database
from app.services.domain_access_service import allow_path


class DomainAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] == '/health':
            return await self.app(scope, receive, send)
        request = Request(scope)
        probe = scope['path'] == '/domain-access'
        path = scope['path']
        if probe:
            path = request.headers.get('x-original-uri', request.query_params.get('path', '/')).split('?', 1)[0]
        try:
            # A cached result for /click must never authorize /admin or poison
            # the host after a denied path. Check the complete policy each time.
            role = await allow_path(get_database(), request.headers.get('host', ''), path)
        except Exception:
            logging.exception('Domain access lookup failed')
            response = Response(status_code=503, headers={'Cache-Control': 'no-store'})
            return await response(scope, receive, send)
        if not role or probe:
            response = (JSONResponse({'role': role}, headers={'Cache-Control': 'no-store'}) if role
                        else Response(status_code=403 if probe else 404, headers={'Cache-Control': 'no-store'}))
            # Nginx auth_request must never enter the visitor rate limiter.
            return await response(scope, receive, send)
        await self.app(scope, receive, send)
