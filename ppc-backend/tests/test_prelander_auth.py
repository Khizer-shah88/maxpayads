"""
Prelander Authorization Service — tests.

Covers the security principle this service exists for: DOMAIN != AUTHORIZATION.
A visitor holding nothing but the prelander URL (slug) must be denied; the
same browser that produced a legitimate Smartlink click must be allowed.
"""
import json
import time

import pytest

from app.services import prelander_auth_service as pas


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeRedis:
    """In-memory async redis subset — setex/get/pipeline/expire."""

    def __init__(self):
        self.store = {}

    async def setex(self, key, ttl, value):
        self.store[key] = (str(value), time.time() + ttl)

    async def get(self, key):
        entry = self.store.get(key)
        if not entry:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            self.store.pop(key, None)
            return None
        return value

    async def keys(self, pattern):
        pre = pattern.rstrip("*")
        return [k for k in self.store if k.startswith(pre)]

    def pipeline(self):
        return FakePipeline(self)

    async def expire(self, key, ttl):
        return key in self.store


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def setex(self, key, ttl, value):
        self.ops.append(("setex", key, ttl, value))
        return self

    async def execute(self):
        for op in self.ops:
            if op[0] == "setex":
                await self.redis.setex(op[1], op[2], op[3])


@pytest.fixture
def redis():
    return FakeRedis()


IP = "203.0.113.9"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
SLUG = "GhEeVl9FRVdJRwoJBwJdSUMHCgg"


# ── creation ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_authorization_writes_session_and_indexes(redis):
    ok = await pas.create_authorization(
        click_id="507f1f77bcf86cd799439011", slug=SLUG, ip=IP, user_agent=UA,
        redis=redis, prelander_host="prelander.example.com",
    )
    assert ok is True

    fp = pas._fingerprint(IP, UA)
    sh = pas._slug_hash(SLUG)

    session_raw = await redis.get(pas._session_key("507f1f77bcf86cd799439011"))
    assert session_raw is not None
    session = json.loads(session_raw)
    assert session["fp"] == fp
    assert session["sh"] == sh
    assert session["ua"] == UA

    # Both O(1) indexes exist and name the click
    assert await redis.get(pas._fp_key(fp)) == "507f1f77bcf86cd799439011"
    assert await redis.get(pas._sh_key(sh)) == "507f1f77bcf86cd799439011"


@pytest.mark.asyncio
async def test_create_authorization_requires_click_slug_redis(redis):
    assert await pas.create_authorization("", SLUG, IP, UA, redis) is False
    assert await pas.create_authorization("click-1", "", IP, UA, redis) is False
    assert await pas.create_authorization("click-1", SLUG, IP, UA, None) is False


@pytest.mark.asyncio
async def test_create_authorization_never_raises_on_bad_redis():
    class BrokenRedis:
        async def setex(self, *a):
            raise RuntimeError("down")

        def pipeline(self):
            raise RuntimeError("down")

    ok = await pas.create_authorization("c1", SLUG, IP, UA, BrokenRedis())
    assert ok is False


# ── validation: the DOMAIN != AUTHORIZATION guarantee ─────────────────────────

@pytest.mark.asyncio
async def test_authorized_browser_can_access(redis):
    await pas.create_authorization("507f1f77bcf86cd799439011", SLUG, IP, UA, redis)
    assert await pas.validate_authorization(SLUG, IP, UA, redis) is True


@pytest.mark.asyncio
async def test_direct_visit_without_session_is_denied(redis):
    """The core security rule: knowing the URL must not be enough."""
    assert await pas.validate_authorization(SLUG, IP, UA, redis) is False


@pytest.mark.asyncio
async def test_authorization_dies_with_ttl(redis):
    await pas.create_authorization("c1", SLUG, IP, UA, redis, ttl=1)
    assert await pas.validate_authorization(SLUG, IP, UA, redis) is True
    # Expire the session — the store honors TTL on read.
    for key, (value, expires_at) in list(redis.store.items()):
        redis.store[key] = (value, time.time() - 1)
    assert await pas.validate_authorization(SLUG, IP, UA, redis) is False


@pytest.mark.asyncio
async def test_different_browser_same_ip_is_denied(redis):
    """Another machine behind the same NAT IP cannot ride the session."""
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    other_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605"
    assert await pas.validate_authorization(SLUG, IP, other_ua, redis) is False


@pytest.mark.asyncio
async def test_different_ip_same_browser_slug_path_allowed(redis):
    """Mobile IP change mid-flow: same browser, slug-bound, still authorized."""
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    assert await pas.validate_authorization(SLUG, "198.51.100.7", UA, redis) is True


@pytest.mark.asyncio
async def test_authorization_is_slug_bound(redis):
    """An authorized visitor cannot use their session to read another prelander."""
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    other_slug = "Zm90ZXItdGhpcy1pcy1hbm90aGVyLXNsdWctdmFsdWU"
    assert await pas.validate_authorization(other_slug, IP, UA, redis) is False


@pytest.mark.asyncio
async def test_forged_cookie_reference_is_denied(redis):
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    forged = "c1.deadbeefdeadbeefdeadbeefdeadbeef"
    assert await pas.validate_authorization(SLUG, IP, UA, redis, cookie_reference=forged) is False


@pytest.mark.asyncio
async def test_valid_cookie_reference_authorizes(redis):
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    reference = pas.session_reference("c1", IP, UA)
    assert reference and "." in reference
    # A forged fingerprint inside the reference is caught at parse time.
    assert pas.parse_session_reference(reference, "203.0.113.9", UA) == "c1"
    assert pas.parse_session_reference(reference, "203.0.113.8", UA) is None


@pytest.mark.asyncio
async def test_stolen_cookie_reference_other_browser_denied(redis):
    """A leaked reference is worthless without the originating browser."""
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    reference = pas.session_reference("c1", IP, UA)
    other_ua = "Mozilla/5.0 (X11; Linux x86_64) Firefox/121.0"
    assert await pas.validate_authorization(
        SLUG, IP, other_ua, redis, cookie_reference=reference,
    ) is False


@pytest.mark.asyncio
async def test_redis_unavailable_fails_closed(redis):
    assert await pas.validate_authorization(SLUG, IP, UA, None) is False


# ── session reference signing ─────────────────────────────────────────────────

def test_session_reference_round_trip():
    ref = pas.session_reference("c1", IP, UA)
    assert pas.parse_session_reference(ref, IP, UA) == "c1"


def test_session_reference_empty_click():
    assert pas.session_reference("", IP, UA) == ""


def test_session_reference_malformed():
    assert pas.parse_session_reference("no-dot-here", IP, UA) is None
    assert pas.parse_session_reference(".leading", IP, UA) is None
    assert pas.parse_session_reference("trailing.", IP, UA) is None
    assert pas.parse_session_reference("", IP, UA) is None


def test_fingerprint_differs_by_ua_and_ip():
    assert pas._fingerprint(IP, UA) != pas._fingerprint(IP, UA + "x")
    assert pas._fingerprint(IP, UA) != pas._fingerprint("203.0.113.10", UA)


def test_slug_hash_is_non_reversible_short():
    h = pas._slug_hash(SLUG)
    assert len(h) == 24
    assert SLUG not in h