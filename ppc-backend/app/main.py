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
from app.middleware.domain_access_middleware import DomainAccessMiddleware
from app.middleware.security_middleware import SecurityMiddleware
from app.middleware.capacity import CapacityMiddleware

from app.routers import (
    auth_router, admin_router, publisher_router,
    campaign_router, click_router, withdrawal_router, analytics_router,
)
from app.routers import offer_router, landing_page_router, prelander_router, redirection_domain_router
from app.routers import prelander_public_router
from app.routers import prelander_template_router
from app.routers import direct_link_router, direct_link_stats_router, redirect_chain_router, public_stats_router, stats_profile_router
from app.routers import smartlink_structure_router

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

    # Startup duplicate cleanup & recovery
    try:
        from app.database import get_db
        from app.cache.redis_client import get_redis
        db = get_db()
        redis = get_redis()
        if redis:
            async for k in redis.scan_iter("dup_click:*"):
                await redis.delete(k)
        if db:
            from datetime import datetime, timedelta
            from app.tasks.click_tasks import process_click
            from starlette.concurrency import run_in_threadpool
            since = datetime.utcnow() - timedelta(hours=24)
            bad_clicks = await db.clicks.find({
                "fraud_reason": "duplicate_ip",
                "status": "invalid",
                "timestamp": {"$gte": since},
            }).to_list(200)
            for c in bad_clicks:
                cid = str(c["_id"])
                await db.clicks.update_one(
                    {"_id": c["_id"]},
                    {"$set": {"status": "pending", "is_valid": True, "fraud_reason": None, "processed": False}}
                )
                payload = {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in c.items() if k != "_id"}
                await run_in_threadpool(process_click.delay, cid, payload)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Startup duplicate recovery skipped: {e}")

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
app.add_middleware(SecurityMiddleware)
app.add_middleware(RequestLoggerMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CapacityMiddleware)
app.add_middleware(DomainAccessMiddleware)

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
app.include_router(prelander_public_router.router)  # Public prelander rendering
app.include_router(prelander_template_router.router)  # Admin prelander template CRUD (frontend /admin/prelander-templates)
# direct_link_stats_router BEFORE direct_link_router: it owns the literal
# /direct-links/manual-conversions|stats-profiles|stats/... routes. FastAPI
# matches routes in registration order — with direct_link_router first, its
# GET /{link_id} captured "manual-conversions" as a link id and the Conversion
# History modal failed with "Direct Link not found".
app.include_router(direct_link_stats_router.router)  # Direct link enhanced stats
app.include_router(direct_link_router.router)
app.include_router(redirect_chain_router.router)
app.include_router(smartlink_structure_router.router)
app.include_router(public_stats_router.router)
app.include_router(stats_profile_router.router)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION, "name": settings.APP_NAME}


# /domain-access is handled by the outer domain middleware, before visitor
# throttling and application work, so load cannot consume its visitor quota.


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

    # Use publisher-aware Anchor domain when available
    from app.core.constants import DOMAIN_TYPE_ANCHOR
    from app.services.domain_service import resolve_domain_url
    base_url = await resolve_domain_url(db, DOMAIN_TYPE_ANCHOR, pub)
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
async def root(request: Request):
    """
    Root handler - checks if domain is registered and handles accordingly
    """
    from fastapi.responses import RedirectResponse, Response
    from app.database import get_database
    
    # Get the host
    host = request.headers.get("host", "").lower().split(":")[0]
    
    # Skip if it's localhost or internal
    if host in ("localhost", "127.0.0.1", "0.0.0.0") or host.startswith("192.168."):
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "running",
            "docs": "/docs",
        }
    
    # Check if this domain is registered in admin panel
    db = get_database()
    if db:
        # Check redirection_domains
        domain_doc = await db.redirection_domains.find_one({"domain": host, "status": "active"})
        
        # Also check if it's configured as admin/portal domain
        if not domain_doc:
            system_settings = await db.system_settings.find_one({"key": "platform_domain"})
            admin_domain = system_settings.get("value", "").replace("https://", "").replace("http://", "").split("/")[0] if system_settings else None
            
            # Check stats domain
            stats_domain_doc = await db.system_settings.find_one({"key": "stats_domain"})
            stats_domain = stats_domain_doc.get("value", "").replace("https://", "").replace("http://", "").split("/")[0] if stats_domain_doc else None
            
            # If domain is admin or stats, show API info
            if host in [admin_domain, stats_domain]:
                return {
                    "name": settings.APP_NAME,
                    "version": settings.APP_VERSION,
                    "status": "running",
                    "docs": "/docs",
                }
            
            # If domain is not registered anywhere, close connection
            return Response(content=b"", status_code=444, headers={"Connection": "close"})
        
        # If it's a registered redirection domain
        if domain_doc:
            domain_type = domain_doc.get("domain_type", "")
            
            # If it's an inter or prelander domain accessed directly, redirect
            if domain_type in ("inter", "intermediate", "prelander", "last"):
                # Try to get referrer
                referrer = request.headers.get("referer") or request.headers.get("referrer")
                if referrer and not referrer.startswith(f"http://{host}") and not referrer.startswith(f"https://{host}"):
                    # Redirect to referrer if it's not from the same domain
                    return RedirectResponse(url=referrer, status_code=302)
                else:
                    # Fallback to Google
                    return RedirectResponse(url="https://google.com", status_code=302)
            
            # For anchor domains, show API info
            return {
                "name": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "status": "running",
                "docs": "/docs",
            }
    
    # Default response
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


# Catch-all fallback for unknown/unregistered domains
@app.api_route("/{path:path}", methods=["GET", "POST"], tags=["Fallback"], include_in_schema=False)
async def domain_fallback(request: Request, path: str):
    """
    Fallback handler for:
    1. Unregistered domains pointing to our server - return connection closed (444)
    2. Inter/prelander domains accessed directly - redirect to referrer or Google
    
    Any domain pointing to our server that's not added in admin panel will show no response.
    """
    from fastapi.responses import RedirectResponse, Response
    from app.database import get_database
    
    # Get the host
    host = request.headers.get("host", "").lower().split(":")[0]
    
    # Skip if it's localhost or internal
    if host in ("localhost", "127.0.0.1", "0.0.0.0") or host.startswith("192.168."):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    
    # Check if this domain is registered in admin panel
    db = get_database()
    if db:
        # Check redirection_domains
        domain_doc = await db.redirection_domains.find_one({"domain": host, "status": "active"})
        
        # Also check if it's configured as admin/portal domain
        if not domain_doc:
            system_settings = await db.system_settings.find_one({"key": "platform_domain"})
            admin_domain = system_settings.get("value", "").replace("https://", "").replace("http://", "").split("/")[0] if system_settings else None
            
            # Check stats domain
            stats_domain_doc = await db.system_settings.find_one({"key": "stats_domain"})
            stats_domain = stats_domain_doc.get("value", "").replace("https://", "").replace("http://", "").split("/")[0] if stats_domain_doc else None
            
            # If domain is not registered anywhere, close connection (Nginx 444 equivalent)
            if host not in [admin_domain, stats_domain]:
                # Return empty response with 444 status (Nginx convention for "connection closed without response")
                # FastAPI doesn't support 444, so we use 403 with empty body
                return Response(content=b"", status_code=444, headers={"Connection": "close"})
        
        # If it's a registered redirection domain
        if domain_doc:
            domain_type = domain_doc.get("domain_type", "")
            
            # If it's an inter or prelander domain accessed directly, redirect
            if domain_type in ("inter", "intermediate", "prelander", "last"):
                # Try to get referrer
                referrer = request.headers.get("referer") or request.headers.get("referrer")
                if referrer and not referrer.startswith(f"http://{host}") and not referrer.startswith(f"https://{host}"):
                    # Redirect to referrer if it's not from the same domain
                    return RedirectResponse(url=referrer, status_code=302)
                else:
                    # Fallback to Google
                    return RedirectResponse(url="https://google.com", status_code=302)
    
    # Database unavailable or other cases - return empty response
    return Response(content=b"", status_code=444, headers={"Connection": "close"})
