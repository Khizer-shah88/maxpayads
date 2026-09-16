"""
Regression: middleware must never crash a response that carries cookies.

The bug (user-reported twice): /click?pub=…&site=… returned
{"success": false, "error": "Internal server error"} on the publisher's page.
Root cause: SessionSecurityMiddleware called response.headers.pop("Set-Cookie"),
but Starlette's MutableHeaders has NO .pop() method — AttributeError fired on
EVERY response carrying a Set-Cookie header, AFTER the endpoint had already
succeeded. The /click endpoint only began setting a cookie (the prelander
authorization reference, mpa_pla) when the prelander-auth work landed, which is
exactly when the 500s started appearing on the redirection-domain flow.

This suite builds the middleware stack exactly as app.main does and proves a
cookie-setting route returns its response untouched (302 with Set-Cookie), not
a 500.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.middleware.security_middleware import (
    SecurityHeadersMiddleware,
    RequestValidationMiddleware,
    SecurityAuditMiddleware,
    SessionSecurityMiddleware,
    APISecurityMiddleware,
)


def build_app() -> FastAPI:
    """Mirror app.main's middleware stack (registration order reversed)."""
    app = FastAPI()

    # main.py adds: RequestValidation, SecurityAudit, SessionSecurity,
    # APISecurity, then SecurityHeaders last (outermost).
    app.add_middleware(APISecurityMiddleware)
    app.add_middleware(SessionSecurityMiddleware)
    app.add_middleware(SecurityAuditMiddleware)
    app.add_middleware(RequestValidationMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/click")
    async def click():
        # Exactly what the real /click returns: a redirect that ALSO sets a
        # cookie (the prelander authorization reference).
        response = RedirectResponse(url="https://example.com/d/abc", status_code=302)
        response.set_cookie(
            key="mpa_pla",
            value="token.signature",
            max_age=360,
            httponly=True,
            samesite="lax",
            secure=True,
        )
        return response

    @app.get("/plain")
    async def plain():
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_click_with_cookie_is_not_500():
    """THE regression: a Set-Cookie response must pass through the stack."""
    from httpx import ASGITransport, AsyncClient

    app = build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/click", follow_redirects=False)
    assert resp.status_code == 302, (
        f"/click returned {resp.status_code} — middleware is crashing cookie responses again"
    )
    # The cookie survived and carries the hardening attributes
    set_cookies = resp.headers.get_list("set-cookie")
    assert any("mpa_pla=" in c for c in set_cookies)
    for c in set_cookies:
        if "mpa_pla=" in c:
            assert "httponly" in c.lower()
            assert "samesite" in c.lower()


@pytest.mark.asyncio
async def test_plain_response_still_works():
    from httpx import ASGITransport, AsyncClient

    app = build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/plain")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_multiple_cookies_all_preserved():
    """Two Set-Cookie headers (e.g. anchor ref + browsing session) must both
    survive the rewrite — duplicate headers are the exact case the old
    pop() approach was mishandling."""
    from httpx import ASGITransport, AsyncClient
    from app.middleware.security_middleware import SessionSecurityMiddleware

    app = FastAPI()
    app.add_middleware(SessionSecurityMiddleware)

    @app.get("/multi")
    async def multi():
        response = RedirectResponse(url="https://example.com", status_code=302)
        response.set_cookie(key="mpa_pla", value="a.b", httponly=True)
        response.set_cookie(key="mpa_pls", value="c.d", httponly=True)
        return response

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/multi", follow_redirects=False)
    assert resp.status_code == 302
    set_cookies = resp.headers.get_list("set-cookie")
    assert len(set_cookies) == 2
    assert any("mpa_pla=" in c for c in set_cookies)
    assert any("mpa_pls=" in c for c in set_cookies)