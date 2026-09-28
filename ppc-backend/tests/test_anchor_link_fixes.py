"""
Anchor-link crash regressions.

The reported failure: Smartlinks like
    https://anchor1.trustedcloudmedia.com/click?tag=PUB_8d2n5Uwt
"crashed" the site — the visitor ended on a dead/fallback page instead of
flowing through the redirect chain. Three independent defects caused it:

1. resolve_publisher_id could NOT resolve a PUB_-prefixed id whose random part
   is stored bare (PUB_PREFIX = ""). Every prefixed Smartlink resolved to
   None → "unknown_publisher" → fallback URL.
2. stage_identify_publisher passed the pipeline CONTEXT (not the redis client)
   to the hot-path caches; the first cache read then raised AttributeError —
   a 500 on the /click hot path.
3. click_router's cookie block referenced `ctx` after the except path — a
   NameError waiting for the pipeline to fail.

These tests pin all three, plus the prelander endpoints' new
never-500 guard behaviour.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.dependencies import get_db
from app.services import redirect_pipeline as rp
from app.services.redirect_pipeline import (
    STAGE_IDENTIFY,
    RedirectResolutionContext,
)
from app.utils.public_id_utils import resolve_publisher_id


# ── fakes ─────────────────────────────────────────────────────────────────────

class PubCollection:
    def __init__(self, docs=()):
        self.docs = list(docs)

    async def find_one(self, query, *args, **kwargs):
        for doc in self.docs:
            if doc.get("public_id") == query.get("public_id"):
                return doc
            if doc.get("_id") == query.get("_id"):
                return doc
        return None


class FakeRedis:
    """Minimal async redis: get/setex only (what cached_json touches)."""

    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def exists(self, key):
        return 1 if key in self.store else 0

    async def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key, ttl):
        return key in self.store


def make_ctx(**overrides):
    defaults = dict(
        raw_pub="PUB_8d2n5Uwt",
        raw_site=None,
        ip="203.0.113.9",
        user_agent="Mozilla/5.0 (Windows NT 10.0)",
        referrer="",
        headers={},
    )
    defaults.update(overrides)
    return RedirectResolutionContext(**defaults)


# ── 1. PUB_-prefixed ids resolve ──────────────────────────────────────────────

async def test_prefixed_publisher_id_resolves_to_bare_stored_id():
    """`PUB_8d2n5Uwt` (link spelling) must resolve when the DB stores `8d2n5Uwt`.

    This is the exact reported link format. PUB_PREFIX is "" — the stored
    public_id has no prefix — so the prefixed spelling MUST fall through to
    the prefix-stripped lookup.
    """
    db = SimpleNamespace(publishers=PubCollection([
        {"_id": "507f1f77bcf86cd799439011", "public_id": "8d2n5Uwt", "role": "publisher"},
    ]))
    resolved = await resolve_publisher_id(db, "PUB_8d2n5Uwt")
    assert resolved == "507f1f77bcf86cd799439011"


async def test_bare_publisher_id_still_resolves():
    """The bare 8-char spelling keeps working (new format)."""
    db = SimpleNamespace(publishers=PubCollection([
        {"_id": "507f1f77bcf86cd799439011", "public_id": "8d2n5Uwt"},
    ]))
    assert await resolve_publisher_id(db, "8d2n5Uwt") == "507f1f77bcf86cd799439011"


async def test_legacy_prefixed_storage_still_resolves():
    """Old installs that stored the full `PUB_xxxxxxxx` keep resolving too."""
    db = SimpleNamespace(publishers=PubCollection([
        {"_id": "507f1f77bcf86cd799439022", "public_id": "PUB_8d2n5Uwt"},
    ]))
    assert await resolve_publisher_id(db, "PUB_8d2n5Uwt") == "507f1f77bcf86cd799439022"


async def test_unknown_publisher_still_returns_none():
    db = SimpleNamespace(publishers=PubCollection([]))
    assert await resolve_publisher_id(db, "PUB_NOSUCHXX") is None
    assert await resolve_publisher_id(db, "") is None


# ── 2. the pipeline must pass a REAL redis handle ──────────────────────────────

async def test_identify_publisher_uses_redis_client_not_context(monkeypatch):
    """stage_identify_publisher must never hand the CONTEXT to the caches.

    The historical call `resolve_publisher_id_cached(db, _redis_or_none(ctx), ...)`
    passed the RedirectResolutionContext; its first cache read raised
    AttributeError → a 500 on /click. With a real FakeRedis the lookup both
    works and actually populates the cache.
    """
    from bson import ObjectId

    publisher_oid = ObjectId()
    db = SimpleNamespace(
        publishers=PubCollection([
            {"_id": publisher_oid, "public_id": "8d2n5Uwt", "role": "publisher"},
        ])
    )
    redis = FakeRedis()
    # The hot cache is disabled session-wide in conftest; this test verifies
    # the cache itself, so enable it locally.
    monkeypatch.setattr(settings, "CLICK_HOT_CACHE", True, raising=False)

    ctx = make_ctx(raw_pub="PUB_8d2n5Uwt")
    ok = await rp.stage_identify_publisher(ctx, db, redis=redis)

    assert ok is True
    assert ctx.publisher_id == str(publisher_oid)
    # The cache key must exist — proving the real client was used, not skipped.
    assert any(k.startswith("kv:pub:") for k in redis.store)
    # And the resolution must have been cached under the PREFIXED spelling.
    assert "kv:pub:PUB_8d2n5Uwt" in redis.store


async def test_identify_publisher_tolerates_a_bogus_redis_handle():
    """A non-redis handle degrades to the plain DB path — never raises."""
    from bson import ObjectId

    publisher_oid = ObjectId()
    db = SimpleNamespace(
        publishers=PubCollection([
            {"_id": publisher_oid, "public_id": "8d2n5Uwt", "role": "publisher"},
        ])
    )

    ctx = make_ctx(raw_pub="PUB_8d2n5Uwt")
    # A context-shaped object has neither get nor setex — must be ignored.
    ok = await rp.stage_identify_publisher(ctx, db, redis=make_ctx())

    assert ok is True
    assert ctx.publisher_id == str(publisher_oid)


async def test_redis_or_none_rejects_context_objects():
    ctx = make_ctx()
    assert rp._redis_or_none(ctx) is None          # dataclass context — not redis
    assert rp._redis_or_none(object()) is None     # any random object
    assert rp._redis_or_none(None) is None
    real = FakeRedis()
    assert rp._redis_or_none(real) is real         # a usable client passes


# ── 3. /click never 500s on a pipeline failure ────────────────────────────────

async def test_click_pipeline_failure_serves_fallback_redirect(monkeypatch):
    """A pipeline exception must yield a 302, never a 500 or a NameError."""
    from app.routers import click_router

    async def exploding_parse(request, db, redis=None):
        raise RuntimeError("structures collection unavailable")

    async def exploding_resolve(ctx, db, redis):
        raise RuntimeError("routing down")

    monkeypatch.setattr(
        "app.services.smartlink_parser.parse_smartlink_from_request", exploding_parse
    )

    app = FastAPI()
    app.include_router(click_router.router)
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    from app.cache import redis_client
    monkeypatch.setattr(redis_client, "get_redis", lambda: FakeRedis())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://anchor.example",
        headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0)"},
    ) as client:
        # Legacy-params recovery path: parse crashed → pub/tag read directly.
        response = await client.get("/click?tag=PUB_8d2n5Uwt")
        assert response.status_code in (302, 200)
        # Never a JSON 500 error page.
        assert "internal server error" not in response.text.lower()


# ── 4. prelander endpoints never 500 ─────────────────────────────────────────

async def test_domain_type_returns_safe_shape_on_backend_failure(monkeypatch):
    """A mid-resolution DB crash answers safe JSON — the /d page stays alive."""
    from app.routers import prelander_router as router

    class ExplodingDB:
        redirection_domains = None

        def __getattr__(self, name):
            raise RuntimeError("mongo unavailable")

    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[get_db] = lambda: ExplodingDB()
    monkeypatch.setattr(
        router, "get_authorized_session", AsyncMock(return_value=object())
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://inter.example",
    ) as client:
        response = await client.get(
            "/prelander/domain-type?host=inter.example&slug=abc123",
            headers={"host": "inter.example"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["domain_type"] == "unknown"
        assert body["prelander_domain"] is None
        assert body["bypass_redirect_url"] is None


async def test_resolve_serves_denied_fallback_on_backend_failure(monkeypatch):
    """resolve_slug wraps the whole flow — a crash denies, never 500s."""
    from app.routers import prelander_router as router

    async def exploding_impl(slug, request, db):
        raise RuntimeError("resolution exploded")

    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    monkeypatch.setattr(router, "_resolve_slug_impl", exploding_impl)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://prelander.example",
    ) as client:
        response = await client.get("/prelander/resolve/some-slug")
        assert response.status_code == 403
        assert "session" in response.text.lower()


# ── 5. cached_json never raises on a bogus handle ────────────────────────────

async def test_cached_json_degrades_to_loader_on_bad_handle():
    from app.cache import kv_cache

    calls = {"n": 0}

    async def loader():
        calls["n"] += 1
        return {"ok": True}

    # A context-like object without get/setex must behave exactly like
    # redis=None — the loader runs, nothing raises.
    result = await kv_cache.cached_json(SimpleNamespace(), "kv:bogus", 60, loader)
    assert result == {"ok": True}
    assert calls["n"] == 1