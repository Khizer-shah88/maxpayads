"""
conftest.py — shared pytest fixtures.

THE CORE PROBLEM THIS SOLVES
═════════════════════════════
Motor (AsyncIOMotorClient) binds its connection pool to the asyncio event
loop that is current when the client is first created. pytest-asyncio 0.23.x
in `auto` mode creates a *new* event loop for every async test function,
even if a session-scoped `event_loop` fixture exists. Any Motor await on a
test's per-function loop deadlocks because pymongo's background monitor
threads are blocked waiting on the *session* loop.

FIX: override the pytest-asyncio loop scope to "session" for every test
via the `pytest_collection_modifyitems` hook. This forces every async test
function to run on the same session loop where Motor was started.

DB ISOLATION
════════════
DB_NAME is overridden to `ppc_network_test` before any app import so tests
never touch the production database. The test DB is wiped before (clean
slate) and after (tidy up) the session.
"""

import asyncio
import os

# Must happen BEFORE any app module is imported at collection time
os.environ["DB_NAME"] = "ppc_network_test"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ── Global loop scope override ────────────────────────────────────────────────
# Force every async test to run on the session-scoped loop.
# Without this, pytest-asyncio 0.23.x creates a new loop per test function
# which conflicts with Motor's session-bound connection pool.

def pytest_collection_modifyitems(items):
    for item in items:
        if isinstance(item, pytest.Function):
            # Add loop_scope="session" to any async test that has the asyncio mark
            # (auto mode adds it automatically, but without loop_scope)
            if hasattr(item, "get_closest_marker"):
                marker = item.get_closest_marker("asyncio")
                if marker is not None:
                    # Re-apply with session scope
                    item.add_marker(
                        pytest.mark.asyncio(loop_scope="session"),
                        append=False,
                    )


# ── One event loop for the whole session ─────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """
    Single event loop for the entire test session.
    Motor's connection pool is created on this loop (via FastAPI lifespan)
    and all tests must use this same loop to avoid 'future attached to
    a different loop' errors.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    # Do NOT call loop.close() — Motor's background threads (server monitor,
    # kill-cursors, RTT) are still running during interpreter teardown.


# ── App client — FastAPI lifespan runs exactly once ──────────────────────────

@pytest_asyncio.fixture(scope="session")
async def async_client():
    """
    Session-scoped HTTPX client. FastAPI lifespan (Motor connect, Redis
    connect, index creation) runs once here at session start.
    Test DB is wiped before yielding (clean slate for every CI run).
    """
    from app.main import app

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

        # Post-session wipe — leave DB clean for next run
        _db = get_database()
        if _db is not None and "test" in str(getattr(_db, "name", "")):
            for coll in await _db.list_collection_names():
                await _db[coll].delete_many({})


# ── Convenience handles (sync — Motor is already connected) ──────────────────

@pytest.fixture(scope="session")
def db(async_client):
    from app.database import get_database
    return get_database()


@pytest.fixture(scope="session")
def redis(async_client):
    from app.cache.redis_client import get_redis
    return get_redis()


# ── Shared test data — session-scoped Motor awaits on session loop ────────────

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
