from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
import os
from contextlib import asynccontextmanager

from app.config import settings
from app.database import connect_db, disconnect_db
from app.cache.redis_client import connect_redis, disconnect_redis
from app.core.exceptions import (
    AppException, app_exception_handler,
    http_exception_handler, general_exception_handler,
)
from app.middleware.request_logger import RequestLoggerMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.redirect_chain_middleware import RedirectChainMiddleware
from app.middleware.security_middleware import (
    SecurityHeadersMiddleware,
    RequestValidationMiddleware,
    SecurityAuditMiddleware,
    SessionSecurityMiddleware,
    APISecurityMiddleware,
)

from app.routers import (
    auth_router, admin_router, publisher_router,
    campaign_router, click_router, withdrawal_router, analytics_router,
)
from app.routers import offer_router, landing_page_router, prelander_router, redirection_domain_router
from app.routers import prelander_template_router, prelander_public_router
from app.routers import direct_link_router, direct_link_stats_router, redirect_chain_router, public_stats_router, stats_profile_router

from fastapi.exceptions import HTTPException


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_db()
    await connect_redis()

    # Load ML model
    try:
        from app.ml.isolation_forest_model import fraud_model
        fraud_model.load()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"ML model load failed: {e}")

    yield

    # Shutdown
    await disconnect_db()
    await disconnect_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Max Pay Ads Platform API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware (order matters - first added wraps last)
app.add_middleware(SecurityHeadersMiddleware)  # Outermost - adds security headers
app.add_middleware(RequestValidationMiddleware)  # Validate requests early
app.add_middleware(SecurityAuditMiddleware)  # Audit security events
app.add_middleware(SessionSecurityMiddleware)  # Session security
app.add_middleware(APISecurityMiddleware)  # API security checks
app.add_middleware(RedirectChainMiddleware)
app.add_middleware(RequestLoggerMiddleware)
app.add_middleware(RateLimitMiddleware)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Static file serving (uploads)
_uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(_uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_uploads_dir), name="uploads")

# Routers
app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(publisher_router.router)
app.include_router(campaign_router.router)
app.include_router(click_router.router)
app.include_router(withdrawal_router.router)
app.include_router(analytics_router.router)
app.include_router(offer_router.router)
app.include_router(landing_page_router.router)
app.include_router(prelander_router.router)
app.include_router(redirection_domain_router.router)
app.include_router(prelander_template_router.router)
app.include_router(prelander_public_router.router)  # Public prelander rendering
app.include_router(direct_link_router.router)
app.include_router(direct_link_stats_router.router)  # Direct link enhanced stats
app.include_router(redirect_chain_router.router)
app.include_router(public_stats_router.router)
app.include_router(stats_profile_router.router)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION, "name": settings.APP_NAME}


@app.get("/ad.js", response_class=PlainTextResponse, tags=["Ad Server"])
async def serve_ad(
    request: Request,
    pub: str = "",
    site: str = "",
    type: str = "banner",
):
    """Serve JavaScript ad embed code."""
    from app.database import get_database
    from app.cache.redis_client import get_redis
    from app.services.ad_server import serve_ad_js

    db = get_database()
    redis = get_redis()

    # Use publisher-aware link domain when available
    from app.services.domain_service import resolve_domain_url
    base_url = await resolve_domain_url(db, "link", pub)
    if not base_url:
        domain_doc = await db.system_settings.find_one({"key": "platform_domain"})
        if domain_doc and domain_doc.get("value"):
            base_url = domain_doc["value"].rstrip("/")
        else:
            fallback = str(request.base_url).rstrip("/")
            if any(p in fallback for p in ["fastapi", "backend", "api-service", "host.docker.internal"]):
                base_url = "https://YOUR-DOMAIN.com"
            else:
                base_url = fallback

    js_code = await serve_ad_js(pub, site, base_url, db, redis, ad_type=type)
    return PlainTextResponse(content=js_code, media_type="application/javascript")


@app.get("/", tags=["System"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }
