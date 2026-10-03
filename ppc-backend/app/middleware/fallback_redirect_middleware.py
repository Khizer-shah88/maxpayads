"""
Fallback Redirect Middleware

Handles requests to inter/prelander domains that are accessed directly
at their bare root path (e.g. https://check3.clicklyspot.icu/).

Any sub-path (e.g. /p/render, /d/slug) is allowed through so the real
router can serve it.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import RedirectResponse, Response
import logging

logger = logging.getLogger(__name__)

# Import at module level so tests can monkeypatch it
from app.database import get_database


def _fallback_url() -> str:
    try:
        from app.config import get_settings
        raw = (get_settings().ENTRY_FALLBACK_URL or '').strip()
        if raw:
            return raw
    except Exception:
        pass
    return 'https://www.google.com/'


# All path prefixes that must always reach the router — never intercepted.
_PASS_THROUGH_PREFIXES = (
    "/api/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/uploads/",
    "/auth/",
    "/admin/",
    "/publisher/",
    "/campaigns",
    "/direct-links",
    "/deploy/",
    # Prelander + inter chain paths
    "/p/",           # /p/render?token=...  (prelander renderer)
    "/d/",           # /d/{slug}  (inter domain loader / next.js page)
    # All remaining API routes (Nginx may or may not strip /api prefix)
    "/landing-pages",
    "/offers",
    "/redirect-chains",
    "/prelander-templates",
    "/prelander",
    "/smartlink",
    "/analytics",
    "/withdrawals",
    "/geo-rules",
    "/public-stats",
    "/stats-profiles",
    "/redirection-domains",
    "/click",
    "/ad.js",
    "/health",
    "/domain-access",
)

# Hosts that always pass through without any DB check
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "testserver", ""}


class FallbackRedirectMiddleware(BaseHTTPMiddleware):
    """
    Intercepts bare-root (/) requests on inter/prelander domains and
    redirects them to the referrer or the configured fallback URL.

    Any domain not registered in the admin panel gets a 444 (no response)
    so browsers show "site can't be reached" instead of a 404 page.
    """

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower().split(":")[0]

        # ── 1. Skip local / test hosts ────────────────────────────────────
        if (
            host in _LOCAL_HOSTS
            or host.startswith("192.168.")
            or host.startswith("10.")
            or host.startswith("172.")
            or "test" in host.lower()
        ):
            return await call_next(request)

        # ── 2. Skip known API / router paths ─────────────────────────────
        path = request.url.path
        if any(path == p or path.startswith(p) for p in _PASS_THROUGH_PREFIXES):
            return await call_next(request)

        # ── 3. Only intercept bare root access — all other paths pass through
        #       (e.g. /p/render, /d/slug, /favicon.ico …)
        if path not in ("/", ""):
            return await call_next(request)

        # ── 4. DB lookup: is this domain registered? ──────────────────────
        try:
            db = get_database()
            if db is None:
                return await call_next(request)

            domain_doc = await db.redirection_domains.find_one(
                {"domain": host, "status": "active"}
            )

            if not domain_doc:
                # Check admin / stats domain from system_settings
                s = await db.system_settings.find_one({"key": "platform_domain"})
                admin_domain = (
                    s.get("value", "")
                    .replace("https://", "").replace("http://", "")
                    .split("/")[0]
                    if s else None
                )
                sd = await db.system_settings.find_one({"key": "stats_domain"})
                stats_domain = (
                    sd.get("value", "")
                    .replace("https://", "").replace("http://", "")
                    .split("/")[0]
                    if sd else None
                )

                if host in (admin_domain, stats_domain):
                    return await call_next(request)

                # Completely unregistered domain → no response
                logger.info(f"Unregistered domain blocked: {host}")
                return Response(
                    content=b"",
                    status_code=444,
                    headers={"Connection": "close"},
                )

            # ── 5. Registered domain — handle by type ─────────────────────
            domain_type = domain_doc.get("domain_type", "")

            if domain_type in ("inter", "intermediate", "prelander", "last"):
                # Bare root access to an inter/prelander domain → redirect away
                referrer = (
                    request.headers.get("referer")
                    or request.headers.get("referrer")
                    or ""
                )
                if referrer and not referrer.startswith(
                    (f"http://{host}", f"https://{host}")
                ):
                    logger.info(f"{host}/ → referrer {referrer}")
                    return RedirectResponse(url=referrer, status_code=302)

                fallback = _fallback_url()
                logger.info(f"{host}/ → fallback {fallback}")
                return RedirectResponse(url=fallback, status_code=302)

            # Anchor or unknown type — let the normal app handle it
            return await call_next(request)

        except Exception as exc:
            logger.error(f"FallbackRedirectMiddleware error: {exc}")
            return await call_next(request)
