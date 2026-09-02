"""
conftest.py — shared pytest fixtures.

Motor binds its connection pool to the asyncio event loop current when
AsyncIOMotorClient is first created. All fixtures and tests share a single
session-scoped event loop so Motor's connection pool stays valid for the
entire test run.

DB isolation: DB_NAME is overridden to `ppc_network_test` before any app
import. The test DB is wiped before the session (clean slate) and after
(tidy up for next run).
"""

import asyncio
import os

# Must happen before any app module is imported
os.environ.setdefault("DB_NAME", "ppc_network_test")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app


# ── One event loop for the whole session ─────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def event_loop(event_loop_policy):
    """
    Session-scoped loop shared by every async fixture and test.
    Not explicitly closed — Motor's thread-pool executor needs the loop to
    remain accessible during interpreter shutdown.
    """
    loop = event_loop_policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop


# ── App client — FastAPI lifespan runs once ───────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def async_client():
    """
    Session-scoped AsyncClient. DB/Redis connect once via FastAPI lifespan.
    Wipes the test DB before and after the session.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        from app.database import get_database
        _db = get_database()
        if _db is not None and "test" in str(getattr(_db, "name", "")):
            for coll in await _db.list_collection_names():
                await _db[coll].delete_many({})

        yield ac

        _db = get_database()
        if _db is not None and "test" in str(getattr(_db, "name", "")):
            for coll in await _db.list_collection_names():
                await _db[coll].delete_many({})


# ── DB / Redis handles — synchronous, no await ───────────────────────────────

@pytest.fixture(scope="session")
def db(async_client):
    from app.database import get_database
    return get_database()


@pytest.fixture(scope="session")
def redis(async_client):
    from app.cache.redis_client import get_redis
    return get_redis()


# ── Shared test records — session-scoped so Motor awaits use the session loop ─

@pytest_asyncio.fixture(scope="session")
async def test_admin(db):
    from app.core.security import hash_password
    data = {
        "name": "Test Admin",
        "email": "admin@test.com",
        "password_hash": hash_password("admin123"),
        "role": "admin",
        "status": "active",
        "balance": 0.0,
        "total_earnings": 0.0,
        "revenue_share": 1.0,
    }
    result = await db.publishers.insert_one(data)
    data["_id"] = result.inserted_id
    yield data
    await db.publishers.delete_one({"_id": data["_id"]})


@pytest_asyncio.fixture(scope="session")
async def test_publisher(db):
    from app.core.security import hash_password
    data = {
        "name": "Test Publisher",
        "email": "publisher@test.com",
        "password_hash": hash_password("password123"),
        "role": "publisher",
        "status": "active",
        "balance": 0.0,
        "total_earnings": 0.0,
        "revenue_share": 0.80,
    }
    result = await db.publishers.insert_one(data)
    data["_id"] = result.inserted_id
    yield data
    await db.publishers.delete_one({"_id": data["_id"]})


@pytest_asyncio.fixture(scope="session")
async def test_website(db, test_publisher):
    data = {
        "publisher_id": str(test_publisher["_id"]),
        "domain": "testsite.com",
        "name": "Test Site",
        "status": "active",
        "total_clicks": 0,
        "valid_clicks": 0,
        "invalid_clicks": 0,
        "total_earnings": 0.0,
    }
    result = await db.websites.insert_one(data)
    data["_id"] = result.inserted_id
    yield data
    await db.websites.delete_one({"_id": data["_id"]})


@pytest.fixture(scope="session")
def admin_token(test_admin):
    from app.core.security import create_access_token
    return create_access_token({"sub": str(test_admin["_id"]), "role": "admin"})


@pytest.fixture(scope="session")
def publisher_token(test_publisher):
    from app.core.security import create_access_token
    return create_access_token({"sub": str(test_publisher["_id"]), "role": "publisher"})


@pytest.fixture(scope="session")
def client(async_client):
    return async_client
