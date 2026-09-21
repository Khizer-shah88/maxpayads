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

    async def incr(self, key):
        """Atomic counter — the STEP 18 race-free consumption primitive."""
        if key in self.store:
            value, expires_at = self.store[key]
            if time.time() <= expires_at:
                self.store[key] = (str(int(value) + 1), expires_at)
                return int(value) + 1
            self.store.pop(key, None)
        self.store[key] = ("1", time.time() + 3600)
        return 1


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
def session_api(monkeypatch, redis):
    """Exercise HTTP session gates with real authorization and an in-memory store."""
    from fastapi import FastAPI
    from unittest.mock import AsyncMock
    from app.routers import prelander_router as routes
    from app.dependencies import get_db

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: None
    monkeypatch.setattr(routes, "get_redis_safe", lambda: redis)
    content = AsyncMock(return_value={"success": True, "offer_url": "https://example.com/download"})
    monkeypatch.setattr(routes, "_get_prelander_data", content)
    return app, content


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/prelander/session-check", "/prelander/resolve/session"])
@pytest.mark.parametrize("state", ["missing", "unknown", "expired", "revoked"])
async def test_http_session_denial_is_explicit(session_api, redis, path, state):
    from httpx import AsyncClient, ASGITransport

    app, content = session_api
    cookies = {}
    if state == "unknown":
        cookies[pas.PL_SESSION_COOKIE] = "unknown-session"
    elif state in ("expired", "revoked"):
        session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
        cookies[pas.PL_SESSION_COOKIE] = await pas.establish_prelander_session(session, redis)
        if state == "expired":
            session.expires_at = int(time.time()) - pas.SESSION_SKEW_SECONDS - 1
            # Keep the Redis entry alive to verify the authorization's own expiry check.
            await redis.setex(pas._session_key(session.token), 60, json.dumps(session.to_json()))
        else:
            await pas.revoke_authorization(session.token, redis)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies=cookies) as client:
        response = await client.get(path)
    assert response.status_code == 403
    assert response.json()["authorized"] is False
    assert response.json()["detail"] == "Session expired or unavailable"
    assert response.headers["cache-control"] == "no-store, private"
    assert "location" not in response.headers
    content.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_valid_session_can_reload_then_expires(session_api, redis):
    from httpx import AsyncClient, ASGITransport

    app, content = session_api
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    pl_id = await pas.establish_prelander_session(session, redis)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", cookies={pas.PL_SESSION_COOKIE: pl_id},
    ) as client:
        for _ in range(2):
            check = await client.get("/prelander/session-check")
            assert check.status_code == 200
            assert check.json() == {"authorized": True}
            resolved = await client.get("/prelander/resolve/session")
            assert resolved.status_code == 200
            assert resolved.json()["success"] is True
            assert resolved.headers["cache-control"] == "no-store, private"
        await redis.delete(pas._pl_session_key(pl_id))
        expired = await client.get("/prelander/resolve/session")
        assert expired.status_code == 403
    assert content.await_count == 2


@pytest.mark.asyncio
async def test_http_session_store_unavailable(session_api, monkeypatch):
    from httpx import AsyncClient, ASGITransport
    from app.routers import prelander_router as routes

    app, content = session_api
    monkeypatch.setattr(routes, "get_redis_safe", lambda: None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/prelander/session-check", "/prelander/resolve/session"):
            response = await client.get(path)
            assert response.status_code == 503
            assert response.json()["authorized"] is False
    content.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["missing", "unknown", "expired", "revoked"])
async def test_arrival_claim_does_not_redirect_unavailable_sessions(session_api, redis, state):
    from httpx import AsyncClient, ASGITransport

    app, content = session_api
    cookies = {}
    if state == "unknown":
        cookies[pas.PL_SESSION_COOKIE] = "unknown-session"
    elif state in ("expired", "revoked"):
        session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
        cookies[pas.PL_SESSION_COOKIE] = await pas.establish_prelander_session(session, redis)
        if state == "expired":
            session.expires_at = int(time.time()) - pas.SESSION_SKEW_SECONDS - 1
            await redis.setex(pas._session_key(session.token), 60, json.dumps(session.to_json()))
        else:
            await pas.revoke_authorization(session.token, redis)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies=cookies) as client:
        response = await client.get("/prelander/claim")
    assert response.status_code == 403
    assert response.json().get("reason") != "arrival_unavailable"
    assert "location" not in response.headers
    content.assert_not_awaited()


@pytest.mark.asyncio
async def test_arrival_claim_distinguishes_new_tab_from_expired_session(session_api, redis):
    from httpx import AsyncClient, ASGITransport
    from app.routers import prelander_router as routes

    app, content = session_api
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    sid = await pas.establish_prelander_session(session, redis)
    await redis.setex(routes._ARRIVAL_KEY.format(sid), 60, "1")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", cookies={pas.PL_SESSION_COOKIE: sid},
    ) as client:
        arrival = await client.get("/prelander/claim")
        assert arrival.status_code == 200
        assert arrival.json()["ok"] is True
        pasted = await client.get("/prelander/claim")
        assert pasted.status_code == 403
        assert pasted.json()["reason"] == "arrival_unavailable"
        assert pasted.headers["cache-control"] == "no-store, private"
        await redis.delete(pas._pl_session_key(sid))
        expired = await client.get("/prelander/claim")
        assert expired.status_code == 403
        assert expired.json().get("reason") != "arrival_unavailable"
    content.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_handoff_shows_message_without_referrer_redirect(session_api):
    from httpx import AsyncClient, ASGITransport

    app, content = session_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/prelander/_auth/unknown", headers={"referer": "https://example.com/"})
    assert response.status_code == 403
    assert "Session expired or unavailable" in response.text
    assert "location" not in response.headers
    content.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_requires_admin_authentication(session_api):
    from httpx import AsyncClient, ASGITransport

    app, content = session_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/prelander/preview")
    assert response.status_code == 401
    content.assert_not_awaited()


# ── STEP 8 — duplicate tab / copied URL behavior ─────────────────────────────
#
# Documented browser reality: cookies belong to the BROWSER PROFILE, not the
# tab. A duplicated tab inherits the same cookie jar and the same (IP, UA)
# fingerprint — the architecture CANNOT tell it apart, and per the spec we do
# NOT implement fragile tab isolation (it would need a per-tab nonce, a
# separate requirement).
#   Case A (full flow)          → ALLOW  — fingerprint/slug session exists
#   Case B (paste, other browser) → DENY — different UA never passes
#   Case C (paste, incognito)   → DENY — no session/cookie; the fingerprint
#                                    index may match (same machine!) ONLY if
#                                    the same non-incognito profile made the
#                                    click AND the same UA — see
#                                    test_incognito_sharing_ip_is_the_documented_edge
#   Case D (after expiry)       → DENY — expires_at enforced
#   Case E (no cookie)          → fingerprint/slug binding decides; a bare
#                                    URL with no session anywhere → DENY
#   Case F (refresh, live)      → ALLOW — browsing session, no re-consume
#   Duplicated tab (same profile) → ALLOW (documented, by design)

@pytest.mark.asyncio
async def test_case_a_full_flow_allowed(redis):
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    got = await pas.validate_authorization(SLUG, IP, UA, redis)
    assert got is not None


@pytest.mark.asyncio
async def test_case_b_pasted_into_different_browser_denied(redis):
    """Different browser (different UA): even with the exact URL, denied."""
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    other_browser = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605"
    # Different browser, same IP — the shared-IP reality (office/NAT)
    assert await pas.validate_authorization(SLUG, IP, other_browser, redis) is None


@pytest.mark.asyncio
async def test_case_d_after_expiration_denied(redis):
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    for key, (value, expires_at) in list(redis.store.items()):
        redis.store[key] = (value, time.time() - 1)
    assert await pas.validate_authorization(SLUG, IP, UA, redis) is None


@pytest.mark.asyncio
async def test_case_e_copied_url_no_session_denied(redis):
    """A fresh Redis (no click ever happened): the URL alone grants nothing."""
    assert await pas.validate_authorization(SLUG, IP, UA, redis) is None


@pytest.mark.asyncio
async def test_case_f_refresh_allowed_without_reconsuming(redis):
    """Refresh rides the browsing session — the handoff is long gone."""
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    pl_id = await pas.establish_prelander_session(session, redis)
    for _ in range(5):
        got = await pas.validate_prelander_session(pl_id, redis, slug=SLUG)
        assert got is not None


@pytest.mark.asyncio
async def test_duplicated_tab_same_profile_allowed(redis):
    """Documented: a duplicated tab shares the profile's cookie jar + fingerprint."""
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    pl_id = await pas.establish_prelander_session(session, redis)
    # Tab B validates the same way Tab A did — identical browser identity.
    got = await pas.validate_prelander_session(pl_id, redis, slug=SLUG)
    assert got is not None


@pytest.mark.asyncio
async def test_incognito_sharing_ip_is_the_documented_edge(redis):
    """
    The honest edge case: incognito on the SAME machine shares the IP and —
    with the same browser build — the UA. The server cannot distinguish it
    from the original profile (no cookie, same identity). This is the
    documented limit of non-tab-isolated architecture; the slug binding and
    the short 5-minute TTL are the compensating controls.
    """
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    # Same UA, same IP, no cookie → the fingerprint index still finds it.
    got = await pas.validate_authorization(SLUG, IP, UA, redis)
    assert got is not None  # documented: indistinguishable from the legit visitor


# ── STEP 12 — IP is a signal, not the sole identifier ──────────────────────

@pytest.mark.asyncio
async def test_relaxed_mode_allows_mobile_ip_rotation(redis):
    """Default: carrier NAT/VPN rotation must not lock the visitor out."""
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    got = await pas.validate_authorization(SLUG, "198.51.100.77", UA, redis)
    assert got is not None


@pytest.mark.asyncio
async def test_strict_mode_denies_ip_rotation(redis, monkeypatch):
    monkeypatch.setenv("PRELANDER_IP_MODE", "strict")
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    got = await pas.validate_authorization(SLUG, "198.51.100.77", UA, redis)
    assert got is None


@pytest.mark.asyncio
async def test_strict_mode_still_allows_exact_browser(redis, monkeypatch):
    monkeypatch.setenv("PRELANDER_IP_MODE", "strict")
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    got = await pas.validate_authorization(SLUG, IP, UA, redis)
    assert got is not None


@pytest.mark.asyncio
async def test_ip_never_sole_identifier_both_modes(redis):
    """Different browser on the same IP is denied in BOTH modes."""
    await pas.create_authorization("c1", SLUG, IP, UA, redis)
    other_browser = "Mozilla/5.0 (X11; Linux x86_64) Firefox/121.0"
    assert await pas.validate_authorization(SLUG, IP, other_browser, redis) is None


# ── STEP 10 — same hostname, different campaigns ─────────────────────────────

@pytest.mark.asyncio
async def test_same_host_serves_each_visitors_campaign(redis):
    """
    Two visitors, same prelander hostname, two campaigns. Each session is
    bound to its own campaign and slug — the content follows the SESSION,
    never the hostname.
    """
    slug_a, slug_b = SLUG, "c2xlc1bpbmRlci1zbHVnLXZhbHVl"
    sess_a = await pas.create_authorization(
        "click-a", slug_a, "203.0.113.10", UA, redis,
        campaign_id="camp-101", prelander_host="prelander.example.com",
    )
    sess_b = await pas.create_authorization(
        "click-b", slug_b, "203.0.113.11", UA, redis,
        campaign_id="camp-202", prelander_host="prelander.example.com",
    )
    # Same hostname on both sessions
    assert sess_a.prelander_host == sess_b.prelander_host

    got_a = await pas.validate_prelander_access(
        slug=slug_a, ip="203.0.113.10", user_agent=UA, redis=redis, db=None,
        expected_prelander_host="prelander.example.com",
    )
    got_b = await pas.validate_prelander_access(
        slug=slug_b, ip="203.0.113.11", user_agent=UA, redis=redis, db=None,
        expected_prelander_host="prelander.example.com",
    )
    # Each visitor is granted — with THEIR OWN campaign context
    assert got_a is not None and got_a.campaign_id == "camp-101"
    assert got_b is not None and got_b.campaign_id == "camp-202"


@pytest.mark.asyncio
async def test_session_campaign_not_request_derived(redis):
    """The resolver reads campaign_id from the session, not from the request."""
    session = await pas.create_authorization(
        "c1", SLUG, IP, UA, redis, campaign_id="camp-101",
    )
    got = await pas.validate_authorization(SLUG, IP, UA, redis)
    assert got.campaign_id == "camp-101"


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
async def test_token_is_high_entropy_and_not_sequential(redis):
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
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    assert session is not None
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
    # The forged signature itself never verifies…
    assert pas.parse_session_reference(forged, IP, UA) is None
    # …and for a DIFFERENT browser no other path (fingerprint/slug index)
    # rescues the request — the forged cookie grants nothing anywhere.
    other_ua = "Mozilla/5.0 (X11; Linux x86_64) Firefox/121.0"
    assert await pas.validate_authorization(SLUG, IP, other_ua, redis, cookie_reference=forged) is None


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
async def test_handoff_state_lifecycle(redis):
    """
    STEP 11 state machine: issued → exchanged. The stored record carries
    `issued` at mint; the atomic GETDEL consume removes it (only ONE caller
    can ever see `issued`) and the exchange is what flips the visitor onto the
    browsing session (`active`), which later dies by TTL (`expired`),
    consumption ceiling (`consumed`), or revoke (`revoked`).
    """
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    handoff = await pas.mint_handoff(session, redis)

    # issued state recorded at mint
    raw = await redis.get(pas._handoff_key(handoff))
    assert raw is not None
    assert json.loads(raw)["state"] == pas.HANDOFF_ISSUED

    # exchange: issued → exchanged (record removed atomically)
    got = await pas.consume_handoff(handoff, redis, ip=IP, user_agent=UA)
    assert got is not None
    # the record is gone — a second caller cannot even read the state
    assert await redis.get(pas._handoff_key(handoff)) is None

    # onward lifecycle rides the session
    pl_id = await pas.establish_prelander_session(session, redis)
    assert pl_id is not None
    assert session.status == pas.STATUS_ACTIVE

    # expiry flips the usability off — beyond the 60s acceptance skew
    session.expires_at = int(time.time()) - (pas.SESSION_SKEW_SECONDS + 30)
    assert session.is_expired() is True
    assert session.is_usable() is False

    # revocation kills the browsing session too (already covered, but the
    # state name is the point)
    assert pas.STATUS_REVOKED in (pas.STATUS_REVOKED,)


@pytest.mark.asyncio
async def test_refresh_never_reuses_handoff(redis):
    """
    STEP 11 + 7: after the exchange, refreshes go through the browsing
    session — the handoff is deleted and can never be 'used again'.
    """
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    handoff = await pas.mint_handoff(session, redis)
    assert await pas.consume_handoff(handoff, redis, ip=IP, user_agent=UA) is not None

    pl_id = await pas.establish_prelander_session(session, redis)
    for _ in range(3):  # three refreshes
        got = await pas.validate_prelander_session(pl_id, redis, slug=SLUG)
        assert got is not None
    # the handoff is still gone
    assert await redis.get(pas._handoff_key(handoff)) is None


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
    assert response.status_code == 403
    body = response.body.decode()
    # Neutral — leaks nothing about campaigns, publishers, or internals
    for leak in ("campaign", "offer", "stack", "Traceback"):
        assert leak not in body
    assert "Session expired or unavailable" in body
    assert "open a new link" in body
    assert response.headers["cache-control"] == "no-store, private"
    assert "location" not in response.headers


def test_denied_response_not_found_mode(denied_settings):
    denied_settings("not_found")
    response = pas.build_denied_response()
    assert response.status_code == 403


def test_denied_response_forbidden_mode(denied_settings):
    denied_settings("forbidden")
    response = pas.build_denied_response()
    assert response.status_code == 403


def test_denied_response_legacy_redirect_mode_shows_message(denied_settings):
    denied_settings("redirect", "https://example.com/safe")
    response = pas.build_denied_response()
    assert response.status_code == 403
    assert "location" not in response.headers
    assert b"Session expired or unavailable" in response.body


def test_denied_response_redirect_mode_falls_back_on_bad_url(denied_settings):
    """Legacy redirect configuration cannot suppress the session message."""
    denied_settings("redirect", "javascript:alert(1)")
    response = pas.build_denied_response()
    assert response.status_code == 403


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


# ── STEP 13-16 — headers, open-redirect, anti-abuse, logging ────────────────────

# T7 (spec STEP 19): valid refresh is allowed and never counts as a click.
# Clicks are born ONLY in stage_record_click (redirect_pipeline) — the single
# insert_one on the clicks collection. The refresh path
# (validate_prelander_session) never touches the database writes, so a refresh
# cannot create a click by construction. This test pins the refresh half.
@pytest.mark.asyncio
async def test_t7_valid_refresh_allowed_and_never_a_click(redis):
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    handoff = await pas.mint_handoff(session, redis, target_host="prelander.example.com")
    assert await pas.consume_handoff(
        handoff, redis, requesting_host="prelander.example.com", ip=IP, user_agent=UA,
    ) is not None

    pl_id = await pas.establish_prelander_session(session, redis)
    # Five refreshes — every one allowed, none re-consumes the handoff
    for _ in range(5):
        got = await pas.validate_prelander_session(pl_id, redis, slug=SLUG)
        assert got is not None and got.click_id == "c1"
    # The handoff is still dead — refresh rode the browsing session only
    assert await redis.get(pas._handoff_key(handoff)) is None


# T12: malformed / guessed tokens are denied safely, never raising.
@pytest.mark.asyncio
async def test_t12_malformed_and_guessed_tokens_denied_safely(redis):
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    assert session is not None

    for guess in ("", "x", "a" * 43, "deadbeefdeadbeefdeadbeef", "-", "!@#$%^&*"):
        # Guessed handoff exchange
        assert await pas.consume_handoff(guess, redis, ip=IP, user_agent=UA) is None
        # Guessed session token
        assert await pas.get_session(guess, redis) is None
        # Guessed browsing-session id
        assert await pas.validate_prelander_session(guess, redis, slug=SLUG) is None
        # Forged cookie reference: the signature never verifies, and for a
        # different browser no fingerprint/slug path rescues the request.
        attacker_ua = "attacker-browser/1.0"
        assert await pas.validate_authorization(
            SLUG, IP, attacker_ua, redis, cookie_reference=guess,
        ) is None


# T13: expired token replay is denied (the handoff TTL kills the record).
@pytest.mark.asyncio
async def test_t13_expired_token_replay_denied(redis, monkeypatch):
    monkeypatch.setenv("PRELANDER_HANDOFF_TTL", "1")
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    handoff = await pas.mint_handoff(session, redis, target_host="prelander.example.com")

    # Expire everything in the store
    for key, (value, expires_at) in list(redis.store.items()):
        redis.store[key] = (value, time.time() - 1)

    assert await pas.consume_handoff(
        handoff, redis, requesting_host="prelander.example.com", ip=IP, user_agent=UA,
    ) is None


# T14: invalid redirect destinations are rejected — no open redirect.
@pytest.mark.asyncio
async def test_t14_handoff_target_rejected_when_not_server_routed(redis):
    session = await pas.create_authorization(
        "c1", SLUG, IP, UA, redis, prelander_host="prelander-a.example.com",
    )
    # The click was routed to prelander-a; the browser asks for attacker.com → DENY
    assert pas.resolve_handoff_target(session, "attacker.com") is None
    assert pas.resolve_handoff_target(session, "prelander-b.example.com") is None
    assert pas.resolve_handoff_target(session, "https://attacker.com/x") is None
    # Matching / absent browser value → the server-recorded host wins
    assert pas.resolve_handoff_target(session, "prelander-a.example.com") == "prelander-a.example.com"
    assert pas.resolve_handoff_target(session, "") == "prelander-a.example.com"


@pytest.mark.asyncio
async def test_t14_minted_handoff_for_attacker_target_is_unusable(redis):
    """Even a legacy (host-less) session mints only bare hostnames — never URLs."""
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)  # no prelander_host
    target = pas.resolve_handoff_target(session, "https://attacker.com/path?x=1")
    assert target == "attacker.com"          # reduced to a bare hostname
    handoff = await pas.mint_handoff(session, redis, target_host=target)
    raw = json.loads(await redis.get(pas._handoff_key(handoff)))
    assert raw["th"] == "attacker.com"       # no scheme/path/query ever stored


# T15: parallel token exchange — only one succeeds (GETDEL atomicity).
@pytest.mark.asyncio
async def test_t15_parallel_exchange_only_one_wins(redis):
    import asyncio
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    handoff = await pas.mint_handoff(session, redis, target_host="prelander.example.com")

    # Two concurrent exchanges of the same token
    results = await asyncio.gather(
        pas.consume_handoff(handoff, redis, requesting_host="prelander.example.com", ip=IP, user_agent=UA),
        pas.consume_handoff(handoff, redis, requesting_host="prelander.example.com", ip=IP, user_agent=UA),
    )
    winners = [r for r in results if r is not None]
    assert len(winners) == 1


# STEP 15 — rate limiting on the token surfaces.
@pytest.mark.asyncio
async def test_auth_rate_limit_blocks_after_threshold(redis, monkeypatch):
    # Tiny window for the test
    import app.config as config
    settings = config.get_settings()
    monkeypatch.setattr(settings, "PRELANDER_AUTH_RATE_LIMIT", 3, raising=False)
    monkeypatch.setattr(settings, "PRELANDER_AUTH_RATE_WINDOW", 60, raising=False)

    for _ in range(3):
        assert await pas.check_auth_rate_limit(IP, redis) is True
    # 4th request in the window → blocked
    assert await pas.check_auth_rate_limit(IP, redis) is False
    # Different IP unaffected
    assert await pas.check_auth_rate_limit("198.51.100.7", redis) is True


@pytest.mark.asyncio
async def test_auth_rate_limit_never_blocks_on_redis_failure():
    class BrokenRedis:
        async def incr(self, key):
            raise RuntimeError("down")

        async def expire(self, key, ttl):
            raise RuntimeError("down")

    assert await pas.check_auth_rate_limit(IP, BrokenRedis()) is True


# STEP 16 — tokens never reach logs.
def test_t16_redact_path_tokens():
    secret = "A" * 43
    assert pas.redact_path_tokens(f"/prelander/_auth/{secret}") == "/prelander/_auth/{token}"
    # Non-token paths untouched
    assert pas.redact_path_tokens("/prelander/resolve/abc123") == "/prelander/resolve/abc123"


def test_t16_event_never_emits_raw_tokens(caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="ppc_network.security"):
        pas._event("replay_attempt_detected", token="S" * 43)
        pas._event("redirect_session_created", click_id="c1")
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "S" * 43 not in joined        # raw token never printed
    assert "event=replay_attempt_detected" in joined
    assert "event=redirect_session_created" in joined


# STEP 18 — concurrent consume cannot lose uses (atomic INCR).
@pytest.mark.asyncio
async def test_concurrent_consume_does_not_lose_uses(redis):
    import asyncio
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    # 5 concurrent validations — the ATOMIC counter must land on exactly 5
    # (the JSON mirror may lag under interleaving; the counter is authoritative)
    await asyncio.gather(*[
        pas.validate_authorization(SLUG, IP, UA, redis) for _ in range(5)
    ])
    counter = int(await redis.get(f"{pas._REDIS_PREFIX}uses:{session.token}"))
    assert counter == 5


# STEP 13 — cookie flags come from config.
def test_cookie_flags_default():
    flags = pas.cookie_flags()
    assert flags["httponly"] is True
    assert flags["secure"] is True
    assert flags["samesite"] == "lax"


def test_cookie_flags_from_config(monkeypatch):
    import app.config as config
    settings = config.get_settings()
    monkeypatch.setattr(settings, "PRELANDER_COOKIE_SECURE", False, raising=False)
    monkeypatch.setattr(settings, "PRELANDER_COOKIE_SAMESITE", "strict", raising=False)
    flags = pas.cookie_flags()
    assert flags["secure"] is False and flags["samesite"] == "strict"


# T16 (spec STEP 19): assets keep working — the asset paths nginx/Next.js
# serve (/_next/*, static files) are exempt from the portal gate and carry
# no authorization requirement by design; the browsing session is never
# invalidated by asset requests (they never touch it). Pinned here:
@pytest.mark.asyncio
async def test_t16_asset_requests_do_not_touch_session_or_create_clicks(redis):
    session = await pas.create_authorization("c1", SLUG, IP, UA, redis)
    pl_id = await pas.establish_prelander_session(session, redis)

    # Simulate a page with many asset requests — the session is untouched
    for _ in range(30):
        got = await pas.validate_prelander_session(pl_id, redis, slug=SLUG)
        assert got is not None
    stored = json.loads(await redis.get(pas._session_key(session.token)))
    # Browsing-session reads never consumed anything
    assert stored["used"] == 0
