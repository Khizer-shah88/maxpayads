"""Domain policy and lightweight internal authorization, without user throttling."""
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.cache.redis_client import get_redis
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
            role = await allow_path(get_database(), request.headers.get('host', ''), path,
                                    redis=get_redis())
        except Exception:
            # Deny on a store hiccup (Redis/Mongo blip) with a REAL 403:
            # nginx's auth_request translates any non-2xx/401/403 subrequest
            # status into a bare 500 — behind Cloudflare that surfaces as the
            # flaky "Error 520 — web server is returning an unknown error"
            # the admin saw on intermediate domains. A 403 rides the existing
            # error_page (@domain_denied → 404) and stays deny-safe.
            logging.exception('Domain access lookup failed')
            response = Response(status_code=403, headers={'Cache-Control': 'no-store'})
            return await response(scope, receive, send)
        if not role or probe:
            if role:
                response = JSONResponse(
                    {'role': role},
                    headers={'Cache-Control': 'no-store', 'X-Domain-Known': '1'},
                )
            else:
                response = Response(
                    status_code=403 if probe else 404,
                    headers={'Cache-Control': 'no-store', 'X-Domain-Known': '0'},
                )
            # Nginx auth_request must never enter the visitor rate limiter.
            return await response(scope, receive, send)
        await self.app(scope, receive, send)
