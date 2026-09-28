import logging
import time

from starlette.datastructures import MutableHeaders

logger = logging.getLogger('ppc_network.requests')


class RequestLoggerMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        start = time.perf_counter()

        async def send_response(message):
            if message['type'] == 'http.response.start':
                elapsed = (time.perf_counter() - start) * 1000
                MutableHeaders(scope=message)['X-Process-Time'] = f'{elapsed:.1f}ms'
                if logger.isEnabledFor(logging.INFO):
                    from app.services.prelander_auth_service import redact_path_tokens
                    logger.info('%s %s status=%d time=%.1fms', scope['method'],
                                redact_path_tokens(scope['path']), message['status'], elapsed)
            await send(message)

        await self.app(scope, receive, send_response)
