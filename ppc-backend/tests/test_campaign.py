import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_campaigns_require_admin(async_client: AsyncClient):
    response = await async_client.get("/campaigns")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_campaign_requires_admin(async_client: AsyncClient):
    response = await async_client.post("/campaigns", json={
        "name": "Test Campaign",
        "default_offer_url": "https://example.com",
    })
    assert response.status_code == 401
