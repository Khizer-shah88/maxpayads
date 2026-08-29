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
"""

import asyncio
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
