from fastapi.responses import RedirectResponse, HTMLResponse
from typing import Optional


def build_redirect(
    url: str,
    referrer_suppression: bool = True,
    status_code: int = 302,
) -> HTMLResponse | RedirectResponse:
    """
    Build a redirect response that always strips the referrer.
    Uses an intermediate HTML page with meta referrer policy + meta refresh
    so the destination site never sees the origin/referrer URL.
    """
    if referrer_suppression:
        return _build_noreferrer_redirect(url)
    return RedirectResponse(url=url, status_code=status_code)


def _build_noreferrer_redirect(url: str) -> HTMLResponse:
    """
    Return an intermediate HTML page that strips referrer before redirecting.
    Uses multiple techniques for maximum browser compatibility:
    1. <meta name="referrer" content="no-referrer"> — modern browsers
    2. <meta http-equiv="refresh"> — fallback redirect
    3. window.location.replace() via JS — primary redirect (fastest)
    4. rel="noreferrer" link — manual fallback
    """
    # Escape the URL for safe embedding in HTML
    safe_url = (
        url.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    # Unescaped for JS (escape quotes only)
    js_url = url.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta name="referrer" content="no-referrer">
<meta http-equiv="refresh" content="0;url={safe_url}">
<title>Please wait...</title>
</head>
<body>
<script>window.location.replace("{js_url}");</script>
<noscript><a href="{safe_url}" rel="noreferrer">Click here to continue</a></noscript>
</body>
</html>"""

    return HTMLResponse(
        content=html,
        status_code=200,
        headers={
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


def build_safe_redirect(url: str, fallback: str = "https://example.com") -> str:
    """Validate and return a safe redirect URL."""
    if not url or not url.startswith(("http://", "https://")):
        return fallback
    return url
