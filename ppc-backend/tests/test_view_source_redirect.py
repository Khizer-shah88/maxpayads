"""
Tests for View Source Redirect Middleware

Tests the detection and redirection of view-source requests.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from starlette.testclient import TestClient
from app.middleware.view_source_redirect_middleware import ViewSourceRedirectMiddleware


# Test app with middleware
app = FastAPI()
app.add_middleware(ViewSourceRedirectMiddleware)


@app.get("/")
async def root():
    return {"message": "Welcome"}


@app.get("/p/render")
async def prelander():
    return PlainTextResponse(content="<html><body>Prelander</body></html>")


@app.get("/d/test")
async def inter_domain():
    return PlainTextResponse(content="<html><body>Inter</body></html>")


@app.get("/api/data")
async def api_endpoint():
    return {"data": "test"}


client = TestClient(app)


class TestViewSourceRedirection:
    """Test suite for view-source request detection and redirection"""

    def test_normal_request_passes_through(self):
        """Normal requests should pass through without redirection"""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Welcome"}

    def test_purpose_header_triggers_redirect(self):
        """Purpose: view-source header should trigger 301 redirect"""
        response = client.get(
            "/p/render",
            headers={"purpose": "view-source"},
            follow_redirects=False
        )
        assert response.status_code == 301
        assert "location" in response.headers
        # Should redirect to the same URL without view-source
        assert "/p/render" in response.headers["location"]

    def test_x_purpose_header_triggers_redirect(self):
        """X-Purpose: view-source header should trigger 301 redirect"""
        response = client.get(
            "/d/test",
            headers={"x-purpose": "view-source"},
            follow_redirects=False
        )
        assert response.status_code == 301
        assert "location" in response.headers

    def test_sec_fetch_dest_view_source(self):
        """Sec-Fetch-Dest: view-source should trigger redirect"""
        response = client.get(
            "/p/render",
            headers={"sec-fetch-dest": "view-source"},
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_referer_with_view_source_prefix(self):
        """Referer starting with view-source: should trigger redirect"""
        response = client.get(
            "/p/render",
            headers={"referer": "view-source:https://example.com/"},
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_referrer_with_view_source_prefix(self):
        """Referrer starting with view-source: should trigger redirect"""
        response = client.get(
            "/d/test",
            headers={"referrer": "view-source:https://example.com/"},
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_user_agent_with_view_source(self):
        """User-Agent containing view-source indicators should trigger redirect"""
        response = client.get(
            "/p/render",
            headers={"user-agent": "Mozilla/5.0 (View-Source Extension)"},
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_user_agent_source_viewer(self):
        """User-Agent containing 'source viewer' should trigger redirect"""
        response = client.get(
            "/p/render",
            headers={"user-agent": "Source Viewer Tool/1.0"},
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_normal_api_request_not_blocked(self):
        """API requests with normal Accept headers should pass through"""
        response = client.get(
            "/api/data",
            headers={"accept": "application/json"}
        )
        assert response.status_code == 200
        assert response.json() == {"data": "test"}

    def test_normal_html_request_not_blocked(self):
        """Normal HTML requests should pass through"""
        response = client.get(
            "/p/render",
            headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        assert response.status_code == 200
        assert b"Prelander" in response.content

    def test_plain_text_accept_on_prelander_triggers_redirect(self):
        """Accept: text/plain on prelander paths should trigger redirect"""
        response = client.get(
            "/p/render",
            headers={"accept": "text/plain"},
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_plain_text_accept_on_api_passes_through(self):
        """Accept: text/plain on API paths should pass through (legitimate use)"""
        response = client.get(
            "/api/data",
            headers={"accept": "text/plain"}
        )
        # Should pass through to the API endpoint
        assert response.status_code == 200

    def test_multiple_indicators_trigger_redirect(self):
        """Multiple view-source indicators should trigger redirect"""
        response = client.get(
            "/p/render",
            headers={
                "purpose": "view-source",
                "user-agent": "Source Viewer",
            },
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_redirect_includes_query_params(self):
        """Redirect should preserve query parameters"""
        response = client.get(
            "/p/render?token=abc123&os=windows",
            headers={"purpose": "view-source"},
            follow_redirects=False
        )
        assert response.status_code == 301
        location = response.headers["location"]
        assert "token=abc123" in location
        assert "os=windows" in location

    def test_redirect_cache_headers(self):
        """Redirect response should include no-cache headers"""
        response = client.get(
            "/p/render",
            headers={"purpose": "view-source"},
            follow_redirects=False
        )
        assert response.status_code == 301
        assert response.headers.get("cache-control") == "no-cache, no-store, must-revalidate"
        assert response.headers.get("pragma") == "no-cache"
        assert response.headers.get("expires") == "0"

    def test_case_insensitive_header_detection(self):
        """Header detection should be case-insensitive"""
        response = client.get(
            "/p/render",
            headers={"Purpose": "VIEW-SOURCE"},
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_partial_match_in_purpose_header(self):
        """Purpose header containing 'view-source' anywhere should trigger"""
        response = client.get(
            "/p/render",
            headers={"purpose": "prefetch view-source"},
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_inter_domain_path_detection(self):
        """Inter domain paths (/d/) should be detected as prelander requests"""
        response = client.get(
            "/d/test",
            headers={"purpose": "view-source"},
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_auth_path_detection(self):
        """Auth paths (/_auth/) should be detected as prelander requests"""
        response = client.get(
            "/_auth/token123",
            headers={"accept": "text/plain"},
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_root_path_with_view_source_purpose(self):
        """Root path with view-source purpose should redirect"""
        response = client.get(
            "/",
            headers={"purpose": "view-source"},
            follow_redirects=False
        )
        assert response.status_code == 301

    def test_redirect_url_format(self):
        """Redirect URL should be properly formatted"""
        response = client.get(
            "/p/render",
            headers={"purpose": "view-source"},
            follow_redirects=False
        )
        assert response.status_code == 301
        location = response.headers["location"]
        # Should be a valid URL
        assert location.startswith("http")
        # Should not contain view-source
        assert "view-source" not in location.lower()


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_purpose_header(self):
        """Empty purpose header should not trigger redirect"""
        response = client.get("/", headers={"purpose": ""})
        assert response.status_code == 200

    def test_no_headers(self):
        """Request with no special headers should pass through"""
        response = client.get("/")
        assert response.status_code == 200

    def test_legitimate_source_in_url(self):
        """URLs legitimately containing 'source' should not be blocked"""
        # This would need a route like /data-source, but the middleware
        # should not block it unless it matches view-source patterns
        response = client.get("/api/data")
        assert response.status_code == 200

    def test_normal_browser_headers(self):
        """Normal browser request headers should pass through"""
        normal_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.5",
            "accept-encoding": "gzip, deflate, br",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
        }
        response = client.get("/p/render", headers=normal_headers)
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
