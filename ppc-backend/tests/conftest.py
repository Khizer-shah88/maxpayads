"""
conftest.py — shared pytest fixtures for the FastAPI test suite.

Key problem solved:
  Motor (MongoDB async driver) binds its connection pool to the asyncio event
  loop that was current when AsyncIOMotorClient was first created.  With the
  default per-function event loop scope, every test after the first one gets a
  *new* loop while Motor still holds a reference to the old closed loop →
  RuntimeError: Event loop is closed.

Fix:
  - Set the event loop scope to "session" so all tests share one loop.
  - Provide a session-scoped `async_client` fixture that starts the FastAPI app
    (and therefore the DB/Redis lifespan) exactly once for the whole test run.
  - Tests that need their own client can use `async_client` directly or create
    a fresh AsyncClient inside the same session loop without triggering lifespan.

Test DB isolation:
  - Tests run against `ppc_network_test` (never production `ppc_network`).
  - DB_NAME env var is overridden before the app is imported/started.
  - Session-scoped autouse fixture drops the test database after the suite.
"""

import asyncio
import os

# ── Override DB_NAME BEFORE any app import ─────────────────────────────────
os.environ.setdefault("DB_NAME", "ppc_network_test")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app


# ── Event loop: one loop for the entire test session ─────────────────────────

@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default asyncio policy."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def event_loop(event_loop_policy):
    """
    Session-scoped event loop.  All async fixtures and tests share this loop,
    which keeps the Motor connection pool alive across tests.
    """
    policy = event_loop_policy
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ── Shared HTTP client — app lifespan runs once ───────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def async_client():
    """
    Session-scoped AsyncClient.  The FastAPI lifespan (DB connect, Redis
    connect, ML model load) executes once at the start and tears down once
    at the end of the test session.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


# ── Test DB cleanup — wipe entire test DB after session ──────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def cleanup_test_db(async_client):
    """
    Wipe all collections in the test database after the test session ends.
    The `async_client` fixture is referenced to ensure the DB lifespan is
    already running when we access the database handle.
    """
    yield  # run all tests first
    from app.database import get_database
    db = get_database()
    if db is not None:
        # Only wipe the test database (never allow wiping production)
        db_name = db.name if hasattr(db, "name") else str(db)
        if "test" in str(db_name):
            colls = await db.list_collection_names()
            for coll in colls:
                await db[coll].delete_many({})


# ── Database and test data fixtures ───────────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    """Get database connection for tests."""
    from app.database import get_database
    return get_database()


@pytest_asyncio.fixture
async def redis():
    """Get Redis connection for tests."""
    from app.cache.redis_client import get_redis
    return get_redis()


@pytest_asyncio.fixture
async def test_admin(db):
    """Create a test admin user."""
    from app.core.security import hash_password
    admin_data = {
        "name": "Test Admin",
        "email": "admin@test.com",
        "password_hash": hash_password("admin123"),
        "role": "admin",
        "status": "active",
        "balance": 0.0,
        "total_earnings": 0.0,
        "revenue_share": 1.0,
    }
    result = await db.publishers.insert_one(admin_data)
    admin_data["_id"] = result.inserted_id
    yield admin_data
    # Cleanup
    await db.publishers.delete_one({"_id": admin_data["_id"]})


@pytest_asyncio.fixture
async def test_publisher(db):
    """Create a test publisher."""
    from app.core.security import hash_password
    publisher_data = {
        "name": "Test Publisher",
        "email": "publisher@test.com",
        "password_hash": hash_password("password123"),
        "role": "publisher",
        "status": "active",
        "balance": 0.0,
        "total_earnings": 0.0,
        "revenue_share": 0.80,
    }
    result = await db.publishers.insert_one(publisher_data)
    publisher_data["_id"] = result.inserted_id
    yield publisher_data
    # Cleanup
    await db.publishers.delete_one({"_id": publisher_data["_id"]})


@pytest_asyncio.fixture
async def test_website(db, test_publisher):
    """Create a test website."""
    website_data = {
        "publisher_id": str(test_publisher["_id"]),
        "domain": "testsite.com",
        "name": "Test Site",
        "status": "active",
        "total_clicks": 0,
        "valid_clicks": 0,
        "invalid_clicks": 0,
        "total_earnings": 0.0,
    }
    result = await db.websites.insert_one(website_data)
    website_data["_id"] = result.inserted_id
    yield website_data
    # Cleanup
    await db.websites.delete_one({"_id": website_data["_id"]})


@pytest.fixture
def admin_token(test_admin):
    """Generate JWT token for test admin."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(test_admin["_id"]), "role": "admin"})


@pytest.fixture
def publisher_token(test_publisher):
    """Generate JWT token for test publisher."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(test_publisher["_id"]), "role": "publisher"})


@pytest_asyncio.fixture
async def client(async_client):
    """Alias for async_client for backward compatibility."""
    return async_client