"""
View Source Redirect Middleware

Detects and blocks view-source: requests by redirecting them back to the normal URL.

When a user tries to view the page source using view-source: in the browser,
this middleware intercepts the request and returns a 301 redirect to the normal
URL without the view-source: prefix.

This prevents users from easily viewing the source code of prelander pages.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import RedirectResponse
import logging
import re

logger = logging.getLogger(__name__)


class ViewSourceRedirectMiddleware(BaseHTTPMiddleware):
    """
    Intercepts requests that appear to be view-source attempts and redirects
    them back to the normal URL with a 301 Moved Permanently response.
    
    Detection methods:
    1. Purpose header with "view-source" value (Chromium-based browsers)
    2. X-Purpose header with "view-source" value
    3. Referer/referrer header starting with "view-source:"
    4. Custom detection for other browser indicators
    """

    async def dispatch(self, request: Request, call_next):
        """
        Check incoming request for view-source indicators and redirect if detected.
        """
        
        # ── 1. Check Purpose header (Chromium browsers) ───────────────────
        purpose = request.headers.get("purpose", "").lower()
        x_purpose = request.headers.get("x-purpose", "").lower()
        
        if "view-source" in purpose or "view-source" in x_purpose:
            return self._redirect_to_normal_url(request, "Purpose header")
        
        # ── 2. Check Sec-Fetch-Dest header ────────────────────────────────
        # Some browsers use "view-source" as fetch destination
        fetch_dest = request.headers.get("sec-fetch-dest", "").lower()
        if "view-source" in fetch_dest:
            return self._redirect_to_normal_url(request, "Sec-Fetch-Dest header")
        
        # ── 3. Check Referer/Referrer for view-source: prefix ─────────────
        referrer = (
            request.headers.get("referer", "")
            or request.headers.get("referrer", "")
        )
        if referrer.lower().startswith("view-source:"):
            return self._redirect_to_normal_url(request, "Referer header")
        
        # ── 4. Check if URL path contains view-source patterns ────────────
        # Some proxies or CDNs might pass view-source as a query parameter
        url_str = str(request.url).lower()
        if "view-source" in url_str or "view_source" in url_str:
            # Check if it's in the path or query params
            if re.search(r'[\?&]view[-_]source', url_str):
                return self._redirect_to_normal_url(request, "URL parameter")
        
        # ── 5. Check User-Agent for specific patterns ─────────────────────
        # Some tools or extensions might identify themselves
        user_agent = request.headers.get("user-agent", "").lower()
        view_source_indicators = [
            "source viewer",
            "view-source",
            "htmlviewer",
            "sourceview",
        ]
        if any(indicator in user_agent for indicator in view_source_indicators):
            return self._redirect_to_normal_url(request, "User-Agent")
        
        # ── 6. Check Accept header patterns ───────────────────────────────
        # View source requests might have different Accept headers
        accept = request.headers.get("accept", "").lower()
        # Normal browser requests include text/html with high priority
        # View source might request text/plain or have unusual Accept patterns
        if accept and "text/plain" in accept and "text/html" not in accept:
            # This might be a view-source request, but we need to be careful
            # not to block legitimate API requests
            if self._looks_like_prelander_request(request):
                return self._redirect_to_normal_url(request, "Accept header pattern")
        
        # No view-source detected, continue with normal request processing
        return await call_next(request)
    
    def _looks_like_prelander_request(self, request: Request) -> bool:
        """
        Determine if the request is likely targeting a prelander page.
        
        Returns True if the request path suggests it's for a prelander.
        """
        path = request.url.path
        
        # Prelander paths typically include:
        # - /p/render
        # - /d/{slug}
        # - Direct domain access to prelander domains
        prelander_patterns = [
            r'^/p/',
            r'^/d/',
            r'^/_auth/',
        ]
        
        for pattern in prelander_patterns:
            if re.match(pattern, path):
                return True
        
        return False
    
    def _redirect_to_normal_url(self, request: Request, detection_method: str) -> RedirectResponse:
        """
        Create a 301 redirect response to the normal URL without view-source.
        
        Args:
            request: The incoming request
            detection_method: How the view-source request was detected (for logging)
        
        Returns:
            RedirectResponse with 301 status
        """
        # Construct the normal URL (without view-source)
        url = str(request.url)
        
        # Remove view-source from URL if present
        clean_url = url.replace("view-source:", "").replace("view_source=", "")
        
        # If URL wasn't modified, just use the original URL
        # This handles cases where detection was via headers only
        if clean_url == url:
            # Use the full URL as-is
            clean_url = f"{request.url.scheme}://{request.headers.get('host', '')}{request.url.path}"
            if request.url.query:
                clean_url += f"?{request.url.query}"
        
        logger.info(
            f"View-source request detected ({detection_method}) and redirected: "
            f"{url} → {clean_url}"
        )
        
        # Return 301 Moved Permanently redirect
        return RedirectResponse(
            url=clean_url,
            status_code=301,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
