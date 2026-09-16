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

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            if self.store.pop(key, None) is not None:
                removed += 1
        return removed

    async def getdel(self, key):
        """Atomic GET+DELETE — the single-use handoff guarantee."""
        entry = self.store.pop(key, None)
        if not entry:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            return None
        return value

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
    session = await pas.create_authorization(
        click_id="507f1f77bcf86cd799439011", slug=SLUG, ip=IP, user_agent=UA,
        redis=redis, prelander_host="prelander.example.com",
        publisher_id="pub-1", campaign_id="camp-1", offer_id="off-1",
    )
    assert session is not None

    fp = pas._fingerprint(IP, UA)
    sh = pas._slug_hash(SLUG)

    session_raw = await redis.get(pas._session_key(session.token))
    assert session_raw is not None
    stored = json.loads(session_raw)
    assert stored["fp"] == fp
    assert stored["sh"] == sh
    assert stored["ua"] == UA
    assert stored["pub"] == "pub-1"
    assert stored["camp"] == "camp-1"
    assert stored["offer"] == "off-1"
    assert stored["ph"] == "prelander.example.com"
    assert stored["status"] == pas.STATUS_ACTIVE
    assert stored["exp"] > stored["ts"]

    # Both O(1) indexes exist and name the TOKEN (not a db id)
    assert await redis.get(pas._fp_key(fp)) == session.token
    assert await redis.get(pas._sh_key(sh)) == session.token


@pytest.mark.asyncio
async def test_token_is_high_entropy_and_not_sequential():
    """Spec: cryptographically random identifier — never sequential, never a db id."""
    tokens = set()
    for _ in range(200):
        session = await pas.create_authorization(
            click_id="same-click", slug=SLUG, ip=IP, user_agent=UA, redis=redis,
        )
        assert session is not None
        tokens.add(session.token)
    assert len(tokens) == 200          # all unique
    # Long, url-safe, high-entropy — and nothing like an ObjectId/campaign id
    for token in list(tokens)[:5]:
        assert len(token) >= 40
        assert "507f1f77bcf86cd799439011" not in token
        assert "same-click" not in token


@pytest.mark.asyncio
async def test_internal_context_stored_server_side_not_in_token(redis):
    """The visible handle must not leak any internal routing value."""
    internals = ["camp-1", "off-1", "pub-1", "prelander.example.com"]
    session = await pas.create_authorization(
        click_id="click-9", slug=SLUG, ip=IP, user_agent=UA, redis=redis,
        prelander_host="prelander.example.com",
        publisher_id="pub-1", campaign_id="camp-1", offer_id="off-1",
    )
    for value in internals:
        assert value not in session.token
    # But the session record (server-side) carries them all
    stored = json.loads(await redis.get(pas._session_key(session.token)))
    assert stored["camp"] == "camp-1" and stored["offer"] == "off-1"


@pytest.mark.asyncio
async def test_ttl_comes_from_configuration(monkeypatch, redis):
    """Spec: lifetime via PRELANDER_SESSION_TTL, not hardcoded at call sites."""
    monkeypatch.setenv("PRELANDER_SESSION_TTL", "77")
    session = await pas.create_authorization(
        click_id="c-ttl", slug=SLUG, ip=IP, user_agent=UA, redis=redis,
    )
    assert session.expires_at - session.created_at == 77

    # Explicit per-call override still honored
    session2 = await pas.create_authorization(
        click_id="c-ttl2", slug=SLUG, ip=IP, user_agent=UA, redis=redis, ttl=123,
    )
    assert session2.expires_at - session2.created_at == 123


@pytest.mark.asyncio
async def test_create_authorization_requires_click_slug_redis(redis):
    assert await pas.create_authorization("", SLUG, IP, UA, redis) is None
    assert await pas.create_authorization("click-1", "", IP, UA, redis) is None
    assert await pas.create_authorization("click-1", SLUG, IP, UA, None) is None


@pytest.mark.asyncio
async def test_create_authorization_never_raises_on_bad_redis():
    class BrokenRedis:
        async def setex(self, *a):
            raise RuntimeError("down")

        def pipeline(self):
            raise RuntimeError("down")

    session = await pas.create_authorization("c1", SLUG, IP, UA, BrokenRedis())
    assert session is None


# ── validation: the DOMAIN != AUTHORIZATION guarantee ─────────────────────────

@pytest.mark.asyncio
async def test_authorized_browser_can_access(redis):
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    session = await pas.validate_authorization(SLUG, IP, UA, redis)
    assert session is not None
    # The authorized session carries its internal context for the resolver
    assert session.click_id == "c1"


@pytest.mark.asyncio
async def test_direct_visit_without_session_is_denied(redis):
    """The core security rule: knowing the URL must not be enough."""
    assert await pas.validate_authorization(SLUG, IP, UA, redis) is None


@pytest.mark.asyncio
async def test_authorization_dies_with_ttl(redis, monkeypatch):
    monkeypatch.setenv("PRELANDER_SESSION_TTL", "1")
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    assert session is not None
    assert await pas.validate_authorization(SLUG, IP, UA, redis) is not None
    # Expire the session — the store honors TTL on read.
    for key, (value, expires_at) in list(redis.store.items()):
        redis.store[key] = (value, time.time() - 1)
    assert await pas.validate_authorization(SLUG, IP, UA, redis) is None


@pytest.mark.asyncio
async def test_consumed_session_stops_authorizing(redis):
    """Progression state: an over-used token becomes a dead handle."""
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    for _ in range(pas.MAX_CONSUMPTIONS):
        got = await pas.validate_authorization(SLUG, IP, UA, redis)
        assert got is not None
    # Over the ceiling the status flipped to consumed — no more access.
    stored = json.loads(await redis.get(pas._session_key(session.token)))
    assert stored["status"] == pas.STATUS_CONSUMED
    assert await pas.validate_authorization(SLUG, IP, UA, redis) is None


@pytest.mark.asyncio
async def test_no_consume_keeps_session_alive(redis):
    for _ in range(pas.MAX_CONSUMPTIONS + 5):
        got = await pas.validate_authorization(SLUG, IP, UA, redis, consume=False)
        assert got is not None


@pytest.mark.asyncio
async def test_revoked_session_is_denied(redis):
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    assert await pas.revoke_authorization(session.token, redis) is True
    assert await pas.validate_authorization(SLUG, IP, UA, redis) is None


@pytest.mark.asyncio
async def test_different_browser_same_ip_is_denied(redis):
    """Another machine behind the same NAT IP cannot ride the session."""
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    other_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605"
    assert await pas.validate_authorization(SLUG, IP, other_ua, redis) is None


@pytest.mark.asyncio
async def test_different_ip_same_browser_slug_path_allowed(redis):
    """Mobile IP change mid-flow: same browser, slug-bound, still authorized."""
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    assert await pas.validate_authorization(SLUG, "198.51.100.7", UA, redis) is not None


@pytest.mark.asyncio
async def test_authorization_is_slug_bound(redis):
    """An authorized visitor cannot use their session to read another prelander."""
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    other_slug = "Zm90ZXItdGhpcy1pcy1hbm90aGVyLXNsdWctdmFsdWU"
    assert await pas.validate_authorization(other_slug, IP, UA, redis) is None


@pytest.mark.asyncio
async def test_forged_cookie_reference_is_denied(redis):
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    forged = f"{session.token}.deadbeefdeadbeefdeadbeefdeadbeef"
    assert await pas.validate_authorization(SLUG, IP, UA, redis, cookie_reference=forged) is None


@pytest.mark.asyncio
async def test_valid_cookie_reference_authorizes(redis):
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    reference = pas.session_reference(session.token, IP, UA)
    assert reference and "." in reference
    # A forged fingerprint inside the reference is caught at parse time.
    assert pas.parse_session_reference(reference, IP, UA) == session.token
    assert pas.parse_session_reference(reference, "203.0.113.8", UA) is None


@pytest.mark.asyncio
async def test_stolen_cookie_reference_other_browser_denied(redis):
    """A leaked reference is worthless without the originating browser."""
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    reference = pas.session_reference(session.token, IP, UA)
    other_ua = "Mozilla/5.0 (X11; Linux x86_64) Firefox/121.0"
    assert await pas.validate_authorization(
        SLUG, IP, other_ua, redis, cookie_reference=reference,
    ) is None


@pytest.mark.asyncio
async def test_redis_unavailable_fails_closed():
    assert await pas.validate_authorization(SLUG, IP, UA, None) is None


# ── session reference signing ─────────────────────────────────────────────────

def test_session_reference_round_trip():
    token = pas._new_token()
    ref = pas.session_reference(token, IP, UA)
    assert pas.parse_session_reference(ref, IP, UA) == token


def test_session_reference_empty_token():
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


# ── STEP 4: one-time cross-domain handoff ─────────────────────────────────────

@pytest.mark.asyncio
async def test_handoff_is_opaque_and_carries_no_internal_ids(redis):
    session = await pas.create_authorization(
        "click-42", SLUG, IP, UA, redis,
        publisher_id="pub-9", campaign_id="camp-9", prelander_host="prelander.example.com",
    )
    handoff = await pas.mint_handoff(session, redis, target_host="prelander.example.com")
    assert handoff and len(handoff) >= 40
    # Opaque: no campaign/publisher/db id inside the token
    for internal in ("pub-9", "camp-9", "click-42", "prelander.example.com"):
        assert internal not in handoff


@pytest.mark.asyncio
async def test_handoff_exchange_returns_session(redis):
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    handoff = await pas.mint_handoff(session, redis, target_host="prelander.example.com")
    got = await pas.consume_handoff(
        handoff, redis, requesting_host="prelander.example.com", ip=IP, user_agent=UA,
    )
    assert got is not None and got.token == session.token


@pytest.mark.asyncio
async def test_handoff_is_single_use(redis):
    """Second use (replay, back button, shared link) finds nothing."""
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    handoff = await pas.mint_handoff(session, redis)
    first = await pas.consume_handoff(handoff, redis, ip=IP, user_agent=UA)
    assert first is not None
    second = await pas.consume_handoff(handoff, redis, ip=IP, user_agent=UA)
    assert second is None


@pytest.mark.asyncio
async def test_handoff_target_host_binding(redis):
    """A handoff minted for one prelander domain cannot be exchanged on another."""
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    handoff = await pas.mint_handoff(session, redis, target_host="prelander.example.com")
    got = await pas.consume_handoff(
        handoff, redis, requesting_host="other.example.com", ip=IP, user_agent=UA,
    )
    assert got is None


@pytest.mark.asyncio
async def test_handoff_from_other_browser_denied(redis):
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    handoff = await pas.mint_handoff(session, redis)
    other_ua = "Mozilla/5.0 (X11; Linux x86_64) Firefox/121.0"
    got = await pas.consume_handoff(handoff, redis, ip=IP, user_agent=other_ua)
    assert got is None


@pytest.mark.asyncio
async def test_handoff_dies_with_ttl(redis, monkeypatch):
    monkeypatch.setenv("PRELANDER_HANDOFF_TTL", "1")
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    handoff = await pas.mint_handoff(session, redis)
    for key, (value, expires_at) in list(redis.store.items()):
        redis.store[key] = (value, time.time() - 1)
    assert await pas.consume_handoff(handoff, redis, ip=IP, user_agent=UA) is None


# ── STEP 5/7: prelander-domain browsing session ─────────────────────────────

@pytest.mark.asyncio
async def test_browsing_session_survives_refreshes(redis):
    """STEP 7: after the exchange, refreshes ride the browsing session."""
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    pl_id = await pas.establish_prelander_session(session, redis)
    assert pl_id
    # Many "refreshes" — the id keeps resolving, no consume, no new session
    for _ in range(5):
        got = await pas.validate_prelander_session(pl_id, redis, slug=SLUG)
        assert got is not None and got.token == session.token


@pytest.mark.asyncio
async def test_browsing_session_is_slug_bound(redis):
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    pl_id = await pas.establish_prelander_session(session, redis)
    assert await pas.validate_prelander_session(pl_id, redis, slug="other-slug") is None


@pytest.mark.asyncio
async def test_browsing_session_dies_with_authorization(redis):
    """Revoking the click authorization kills the browsing session too."""
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    pl_id = await pas.establish_prelander_session(session, redis)
    await pas.revoke_authorization(session.token, redis)
    assert await pas.validate_prelander_session(pl_id, redis, slug=SLUG) is None


# ── STEP 6: configurable denied fallback ─────────────────────────────────────

@pytest.fixture
def denied_settings(monkeypatch):
    """Patch the cached settings object's denied-fallback fields per test."""
    settings = pas.get_settings()
    original = {
        "PRELANDER_DENIED_MODE": getattr(settings, "PRELANDER_DENIED_MODE", "generic_page"),
        "PRELANDER_DENIED_FALLBACK_URL": getattr(settings, "PRELANDER_DENIED_FALLBACK_URL", ""),
    }

    def set_mode(mode, url=""):
        monkeypatch.setattr(settings, "PRELANDER_DENIED_MODE", mode, raising=False)
        monkeypatch.setattr(settings, "PRELANDER_DENIED_FALLBACK_URL", url, raising=False)

    yield set_mode
    # monkeypatch auto-restores on teardown


def test_denied_response_default_is_generic_page(denied_settings):
    denied_settings("generic_page")
    response = pas.build_denied_response()
    assert response.status_code == 404
    body = response.body.decode()
    # Neutral — leaks nothing about campaigns, publishers, or internals
    for leak in ("campaign", "offer", "stack", "Traceback"):
        assert leak not in body
    assert "no longer available" in body


def test_denied_response_not_found_mode(denied_settings):
    denied_settings("not_found")
    response = pas.build_denied_response()
    assert response.status_code == 404


def test_denied_response_forbidden_mode(denied_settings):
    denied_settings("forbidden")
    response = pas.build_denied_response()
    assert response.status_code == 403


def test_denied_response_redirect_mode(denied_settings):
    denied_settings("redirect", "https://example.com/safe")
    response = pas.build_denied_response()
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/safe"


def test_denied_response_redirect_mode_falls_back_on_bad_url(denied_settings):
    """Misconfigured redirect target → the generic page, never an unsafe 302."""
    denied_settings("redirect", "javascript:alert(1)")
    response = pas.build_denied_response()
    assert response.status_code == 404


# ── STEP 5: access-middleware orchestrator ─────────────────────────────────────

class FakeClicks:
    """Async clicks collection stub for the click-existence check."""
    def __init__(self, existing=True):
        self.existing = existing

    async def find_one(self, query, projection=None, **kwargs):
        return {"_id": query.get("_id")} if self.existing else None


class FakeDB:
    def __init__(self, existing=True):
        self.clicks = FakeClicks(existing)


@pytest.mark.asyncio
async def test_access_middleware_grants_authorized_browsing_session(redis):
    """Refresh via the browsing session passes the full STEP 5 checklist."""
    session = await pas.create_authorization(
        "c1", SLUG, IP, UA, redis, prelander_host="prelander.example.com",
    )
    pl_id = await pas.establish_prelander_session(session, redis)
    got = await pas.validate_prelander_access(
        slug=SLUG, ip=IP, user_agent=UA, redis=redis, db=FakeDB(),
        pl_session_cookie=pl_id,
        expected_prelander_host="prelander.example.com",
    )
    assert got is not None and got.token == session.token


@pytest.mark.asyncio
async def test_access_middleware_denies_wrong_domain(redis):
    """Check 5: an authorization for one prelander host cannot serve another."""
    session = await pas.create_authorization(
        "c1", SLUG, IP, UA, redis, prelander_host="prelander.example.com",
    )
    pl_id = await pas.establish_prelander_session(session, redis)
    got = await pas.validate_prelander_access(
        slug=SLUG, ip=IP, user_agent=UA, redis=redis, db=FakeDB(),
        pl_session_cookie=pl_id,
        expected_prelander_host="evil.example.com",
    )
    assert got is None


@pytest.mark.asyncio
async def test_access_middleware_denies_wrong_campaign(redis):
    """Check 6: the resolved campaign must match the session's campaign."""
    session = await pas.create_authorization(
        "c1", SLUG, IP, UA, redis, campaign_id="camp-42",
    )
    got = await pas.validate_prelander_access(
        slug=SLUG, ip=IP, user_agent=UA, redis=redis, db=FakeDB(),
        expected_campaign_id="camp-999",
    )
    assert got is None


@pytest.mark.asyncio
async def test_access_middleware_denies_when_click_gone(redis):
    """Check 10: authorization referencing a deleted click is dead."""
    session = await pas.create_authorization("gone-click", SLUG, IP, UA, redis)
    pl_id = await pas.establish_prelander_session(session, redis)
    got = await pas.validate_prelander_access(
        slug=SLUG, ip=IP, user_agent=UA, redis=redis, db=FakeDB(existing=False),
        pl_session_cookie=pl_id,
    )
    assert got is None


@pytest.mark.asyncio
async def test_access_middleware_denies_direct_visit(redis):
    """STEP 6 core: no session, no cookie, no host — nothing is returned."""
    got = await pas.validate_prelander_access(
        slug=SLUG, ip=IP, user_agent=UA, redis=redis, db=FakeDB(),
    )
    assert got is None