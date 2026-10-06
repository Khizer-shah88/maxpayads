#!/usr/bin/env python3
"""
Simple verification script for view-source redirect middleware.
This can be run without pytest to verify the implementation.
"""

import sys
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from starlette.testclient import TestClient

# Add app to path
sys.path.insert(0, '/home/khizershah/Downloads/maxpayads/maxpayads/ppc-backend')

from app.middleware.view_source_redirect_middleware import ViewSourceRedirectMiddleware


def create_test_app():
    """Create a simple test app with the middleware"""
    app = FastAPI()
    app.add_middleware(ViewSourceRedirectMiddleware)
    
    @app.get("/")
    async def root():
        return {"message": "Welcome"}
    
    @app.get("/p/render")
    async def prelander():
        return PlainTextResponse(content="<html><body>Prelander</body></html>")
    
    return app


def test_normal_request():
    """Test that normal requests pass through"""
    app = create_test_app()
    client = TestClient(app)
    
    response = client.get("/")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert response.json() == {"message": "Welcome"}
    print("✅ Normal request passes through")


def test_purpose_header():
    """Test Purpose header detection"""
    app = create_test_app()
    client = TestClient(app)
    
    response = client.get(
        "/p/render",
        headers={"purpose": "view-source"},
        follow_redirects=False
    )
    assert response.status_code == 301, f"Expected 301, got {response.status_code}"
    assert "location" in response.headers
    print("✅ Purpose header triggers redirect")


def test_x_purpose_header():
    """Test X-Purpose header detection"""
    app = create_test_app()
    client = TestClient(app)
    
    response = client.get(
        "/p/render",
        headers={"x-purpose": "view-source"},
        follow_redirects=False
    )
    assert response.status_code == 301, f"Expected 301, got {response.status_code}"
    print("✅ X-Purpose header triggers redirect")


def test_referer_header():
    """Test Referer with view-source prefix"""
    app = create_test_app()
    client = TestClient(app)
    
    response = client.get(
        "/p/render",
        headers={"referer": "view-source:https://example.com/"},
        follow_redirects=False
    )
    assert response.status_code == 301, f"Expected 301, got {response.status_code}"
    print("✅ Referer view-source: prefix triggers redirect")


def test_sec_fetch_dest():
    """Test Sec-Fetch-Dest header"""
    app = create_test_app()
    client = TestClient(app)
    
    response = client.get(
        "/p/render",
        headers={"sec-fetch-dest": "view-source"},
        follow_redirects=False
    )
    assert response.status_code == 301, f"Expected 301, got {response.status_code}"
    print("✅ Sec-Fetch-Dest header triggers redirect")


def test_user_agent():
    """Test User-Agent detection"""
    app = create_test_app()
    client = TestClient(app)
    
    response = client.get(
        "/p/render",
        headers={"user-agent": "Source Viewer Tool/1.0"},
        follow_redirects=False
    )
    assert response.status_code == 301, f"Expected 301, got {response.status_code}"
    print("✅ User-Agent detection triggers redirect")


def test_query_param_preservation():
    """Test that query parameters are preserved in redirect"""
    app = create_test_app()
    client = TestClient(app)
    
    response = client.get(
        "/p/render?token=abc123&os=windows",
        headers={"purpose": "view-source"},
        follow_redirects=False
    )
    assert response.status_code == 301
    location = response.headers["location"]
    assert "token=abc123" in location, f"Token not in location: {location}"
    assert "os=windows" in location, f"OS not in location: {location}"
    print("✅ Query parameters preserved in redirect")


def test_cache_headers():
    """Test that redirect includes no-cache headers"""
    app = create_test_app()
    client = TestClient(app)
    
    response = client.get(
        "/p/render",
        headers={"purpose": "view-source"},
        follow_redirects=False
    )
    assert response.status_code == 301
    assert response.headers.get("cache-control") == "no-cache, no-store, must-revalidate"
    assert response.headers.get("pragma") == "no-cache"
    assert response.headers.get("expires") == "0"
    print("✅ Cache headers present in redirect")


def test_normal_html_request():
    """Test that normal HTML requests are not blocked"""
    app = create_test_app()
    client = TestClient(app)
    
    response = client.get(
        "/p/render",
        headers={
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    )
    assert response.status_code == 200
    assert b"Prelander" in response.content
    print("✅ Normal HTML request not blocked")


def main():
    """Run all verification tests"""
    print("\n" + "="*60)
    print("View Source Redirect Middleware Verification")
    print("="*60 + "\n")
    
    tests = [
        test_normal_request,
        test_purpose_header,
        test_x_purpose_header,
        test_referer_header,
        test_sec_fetch_dest,
        test_user_agent,
        test_query_param_preservation,
        test_cache_headers,
        test_normal_html_request,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ {test.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test.__name__} error: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60 + "\n")
    
    if failed > 0:
        sys.exit(1)
    else:
        print("✨ All verifications passed! Middleware is working correctly.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
