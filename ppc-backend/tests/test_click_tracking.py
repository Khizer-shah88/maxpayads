import pytest
import time
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_click_endpoint_redirects(async_client: AsyncClient):
    """Click endpoint should return either HTTP redirect or HTML redirect shim."""
    response = await async_client.get(
        "/click?pub=test_publisher_123",
        follow_redirects=False,
    )
    assert response.status_code in [200, 302, 307]
    if response.status_code == 200:
        assert "text/html" in response.headers.get("content-type", "").lower()
    else:
        assert "location" in response.headers


@pytest.mark.asyncio
async def test_click_response_speed(async_client: AsyncClient):
    """Click endpoint should respond in under 500ms in the test environment."""
    start = time.time()
    await async_client.get("/click?pub=test_pub", follow_redirects=False)
    elapsed = (time.time() - start) * 1000
    assert elapsed < 500, f"Click endpoint too slow: {elapsed:.1f}ms"


@pytest.mark.asyncio
async def test_ad_js_endpoint(async_client: AsyncClient):
    """Ad.js endpoint should return JavaScript."""
    response = await async_client.get("/ad.js?pub=test&site=test")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "").lower()
    assert "javascript" in content_type or "text/plain" in content_type
