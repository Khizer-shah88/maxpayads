import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from uuid import uuid4


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_register_success():
    unique_email = f"testpub-{uuid4().hex[:8]}@example.com"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/register", json={
            "name": "Test Publisher",
            "email": unique_email,
            "password": "password123",
            "website_domain": "testsite.com",
        })
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert "publisher_id" in data


@pytest.mark.anyio
async def test_register_duplicate_email():
    dup_email = f"duplicate-{uuid4().hex[:8]}@example.com"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First registration
        await client.post("/auth/register", json={
            "name": "Test Publisher",
            "email": dup_email,
            "password": "password123",
        })
        # Duplicate
        response = await client.post("/auth/register", json={
            "name": "Another Publisher",
            "email": dup_email,
            "password": "password456",
        })
    assert response.status_code == 409


@pytest.mark.anyio
async def test_login_invalid_credentials():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "wrongpassword",
        })
    assert response.status_code == 401


@pytest.mark.anyio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
