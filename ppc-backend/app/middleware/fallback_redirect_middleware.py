"""
Fallback Redirect Middleware

Handles requests to inter/prelander domains that are accessed directly.
This middleware runs BEFORE routing, so it catches all requests.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import RedirectResponse, Response
import logging

logger = logging.getLogger(__name__)


class FallbackRedirectMiddleware(BaseHTTPMiddleware):
    """
    Middleware that handles direct access to inter/prelander domains.
    Runs before routing to catch requests that would otherwise 404.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Get the host
        host = request.headers.get("host", "").lower().split(":")[0]
        
        # Skip for localhost/internal IPs
        if host in ("localhost", "127.0.0.1", "0.0.0.0") or host.startswith("192.168."):
            return await call_next(request)
        
        # Skip API routes and system paths - these must reach their handlers
        path = request.url.path
        if (
            path.startswith("/api/")
            or path.startswith("/docs")
            or path.startswith("/redoc")
            or path.startswith("/openapi.json")
            or path.startswith("/uploads/")
            or path in ("/click", "/ad.js", "/health", "/domain-access")
        ):
            return await call_next(request)
        
        # Check if this domain is registered
        try:
            from app.database import get_database
            db = get_database()
            
            if db is None:
                # Database not ready, let request pass through
                return await call_next(request)
            
            # Check if domain is registered in redirection_domains
            domain_doc = await db.redirection_domains.find_one({"domain": host, "status": "active"})
            
            if not domain_doc:
                # Check if it's the admin or stats domain
                system_settings = await db.system_settings.find_one({"key": "platform_domain"})
                admin_domain = None
                if system_settings:
                    admin_domain = system_settings.get("value", "").replace("https://", "").replace("http://", "").split("/")[0]
                
                stats_domain_doc = await db.system_settings.find_one({"key": "stats_domain"})
                stats_domain = None
                if stats_domain_doc:
                    stats_domain = stats_domain_doc.get("value", "").replace("https://", "").replace("http://", "").split("/")[0]
                
                # If it's admin or stats domain, let it pass through
                if host in [admin_domain, stats_domain]:
                    return await call_next(request)
                
                # Unregistered domain - close connection
                logger.info(f"Unregistered domain accessed: {host}")
                return Response(content=b"", status_code=444, headers={"Connection": "close"})
            
            # Domain is registered - check if it's inter or prelander
            domain_type = domain_doc.get("domain_type", "")
            
            if domain_type in ("inter", "intermediate", "prelander", "last"):
                # This is an inter or prelander domain accessed directly
                # Redirect to referrer or Google
                referrer = request.headers.get("referer") or request.headers.get("referrer")
                
                if referrer and not referrer.startswith(f"http://{host}") and not referrer.startswith(f"https://{host}"):
                    # Redirect to referrer
                    logger.info(f"Inter/Prelander domain {host} redirecting to referrer: {referrer}")
                    return RedirectResponse(url=referrer, status_code=302)
                else:
                    # Redirect to Google
                    logger.info(f"Inter/Prelander domain {host} redirecting to Google (no referrer)")
                    return RedirectResponse(url="https://google.com", status_code=302)
            
            # For anchor domains or other types, let the request pass through
            return await call_next(request)
            
        except Exception as e:
            logger.error(f"Error in fallback redirect middleware: {e}")
            # On error, let request pass through
            return await call_next(request)
