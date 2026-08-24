import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("ppc_network.requests")


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000

        logger.info(
            f"{request.method} {request.url.path} "
            f"status={response.status_code} "
            f"time={process_time:.1f}ms "
            f"ip={request.client.host if request.client else 'unknown'}"
        )
        response.headers["X-Process-Time"] = f"{process_time:.1f}ms"
        return response
