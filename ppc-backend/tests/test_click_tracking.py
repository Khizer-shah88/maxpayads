import pytest
import time
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_click_endpoint_redirects():
    """Click endpoint should return either HTTP redirect or HTML redirect shim."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        response = await client.get("/click?pub=test_publisher_123")
    assert response.status_code in [200, 302, 307]
    if response.status_code == 200:
        assert "text/html" in response.headers.get("content-type", "").lower()
    else:
        assert "location" in response.headers


@pytest.mark.anyio
async def test_click_response_speed():
    """Click endpoint should respond quickly (under 500ms for test environment)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        start = time.time()
        response = await client.get("/click?pub=test_pub")
        elapsed = (time.time() - start) * 1000
    # Should be under 500ms in test environment (50ms target in production)
    assert elapsed < 500, f"Click endpoint too slow: {elapsed:.1f}ms"


@pytest.mark.anyio
async def test_ad_js_endpoint():
    """Ad.js endpoint should return JavaScript."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ad.js?pub=test&site=test")
    assert response.status_code == 200
    assert "javascript" in response.headers.get("content-type", "").lower() or \
           "text/plain" in response.headers.get("content-type", "").lower()
