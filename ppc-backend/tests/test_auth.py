import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from uuid import uuid4


@pytest.mark.asyncio
async def test_register_success(async_client: AsyncClient):
    unique_email = f"testpub-{uuid4().hex[:8]}@example.com"
    response = await async_client.post("/auth/register", json={
        "name": "Test Publisher",
        "email": unique_email,
        "password": "password123",
        "website_domain": "testsite.com",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert "publisher_id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(async_client: AsyncClient):
    dup_email = f"duplicate-{uuid4().hex[:8]}@example.com"
    # First registration
    await async_client.post("/auth/register", json={
        "name": "Test Publisher",
        "email": dup_email,
        "password": "password123",
    })
    # Duplicate — must be rejected
    response = await async_client.post("/auth/register", json={
        "name": "Another Publisher",
        "email": dup_email,
        "password": "password456",
    })
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_invalid_credentials(async_client: AsyncClient):
    response = await async_client.post("/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "wrongpassword",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
