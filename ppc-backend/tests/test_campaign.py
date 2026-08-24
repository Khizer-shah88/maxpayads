import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_campaigns_require_admin():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/campaigns")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_create_campaign_requires_admin():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/campaigns", json={
            "name": "Test Campaign",
            "default_offer_url": "https://example.com",
        })
    assert response.status_code == 401
