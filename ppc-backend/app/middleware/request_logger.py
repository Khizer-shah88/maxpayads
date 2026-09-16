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

        # STEP 16 — one-time handoff tokens never reach normal app logs:
        # /prelander/_auth/{secret} logs as /prelander/_auth/{token}.
        logged_path = request.url.path
        if "_auth" in logged_path:
            from app.services.prelander_auth_service import redact_path_tokens
            logged_path = redact_path_tokens(logged_path)

        logger.info(
            f"{request.method} {logged_path} "
            f"status={response.status_code} "
            f"time={process_time:.1f}ms "
            f"ip={request.client.host if request.client else 'unknown'}"
        )
        response.headers["X-Process-Time"] = f"{process_time:.1f}ms"
        return response
