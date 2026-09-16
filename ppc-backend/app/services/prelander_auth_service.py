"""
Prelander Authorization Service
===============================
Server-side authorization for access to protected campaign prelanders.

SECURITY PRINCIPLE: DOMAIN != AUTHORIZATION
Knowing the prelander domain or URL must NOT be sufficient to see the
protected prelander content. Only a visitor who arrived through a legitimate
Smartlink click carries an authorization session, created at click time on the
backend and validated server-side BEFORE any prelander data/HTML is returned.

Flow implemented here (reuses the existing redirect infrastructure):

    Smartlink /click
      → redirect_pipeline resolves campaign/offer/prelander (unchanged)
      → create_authorization()         [session born here, bound to click+ip+ua]
      → Inter /d/{slug}                [browser hop]
      → Prelander /d/{slug}
      → /prelander/resolve/{slug}
      → validate_authorization()       [server-side decision]
          valid   → prelander data returned (existing behavior)
          invalid → None → caller renders the neutral "not available" page

Storage: Redis (existing client, `redis_client.get_redis()`), TTL-bounded so
authorization dies with the session window. No new collections, no schema
changes — the session references the existing click id.

Binding model (cross-domain reality):
  Redirect hosts (Anchor/Inter) and prelander hosts are typically DIFFERENT
  registrar-level domains, so a cookie set on the anchor is not readable on
  the prelander. The browser identity that DOES travel across domains is the
  (client IP, User-Agent) pair — the same identity the existing fraud
  fingerprint (redirect_pipeline.to_click_fields) already trusts. The session
  is therefore keyed by the click id and validated against the visitor's
  IP + UA fingerprint, with the slug hash pinning WHICH prelander route the
  authorization covers.

  A cookie is ALSO set (HttpOnly, SameSite=Lax) as a second binding factor
  when the prelander runs on the same parent domain, but it is never required
  — validation succeeds on IP+UA alone so the normal cross-domain flow keeps
  working untouched.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Configuration (environment-driven, never hardcoded at call sites) ────────

# Session lifetime. Configurable via PRELANDER_SESSION_TTL (seconds).
# Default 300s (5 minutes) per the security spec — the redirect chain
# (click → inter dwell → prelander) completes well within that window. The
# slug itself carries the longer 1h route validity; authorization is the
# shorter-lived of the two by design: a stale route with a dead session is
# still a dead route.
from app.config import get_settings


def _session_ttl() -> int:
    """Authorization lifetime in seconds, from settings/env (PRELANDER_SESSION_TTL)."""
    import os
    raw = os.getenv("PRELANDER_SESSION_TTL", "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            logger.warning("[PRELANDER-AUTH] Invalid PRELANDER_SESSION_TTL=%r, using settings", raw)
    configured = getattr(get_settings(), "PRELANDER_SESSION_TTL", 0)
    if configured and int(configured) > 0:
        return int(configured)
    return 300  # 5 minutes — spec default


# Allowed clock skew (seconds) when comparing session timestamps.
SESSION_SKEW_SECONDS = 60

# Redis key namespaces. Session keyed by the random TOKEN (never a DB id) +
# two O(1) lookup indexes so validation never needs a KEYS scan (KEYS blocks
# Redis; banned in production).
_REDIS_PREFIX = "prelander_auth:"    # token -> session JSON
_FP_PREFIX = "prelander_auth_fp:"   # fingerprint -> token (string)
_SH_PREFIX = "prelander_auth_sh:"   # slug-hash  -> token (string)

# Cookie carrying the authorization reference. HttpOnly + SameSite=Lax.
COOKIE_NAME = "mpa_pla"


def cookie_ttl_seconds() -> int:
    return _session_ttl() + SESSION_SKEW_SECONDS


# Secret for HMAC key derivation. Reuses REDIRECT_SECRET_KEY / SECRET_KEY via
# app.config settings (same policy as prelander_service.REDIRECT_SECRET) so no
# new secrets need to be provisioned.
_SECRET_CACHE: dict = {"secret": None}


def _auth_secret() -> str:
    """Authorization HMAC secret — dedicated key, falling back to the app secret."""
    cached = _SECRET_CACHE.get("secret")
    if cached:
        return cached
    import os
    from app.config import get_settings
    configured = (get_settings().REDIRECT_SECRET_KEY or "").strip()
    if not configured:
        configured = os.getenv("REDIRECT_SECRET_KEY", "").strip()
    if not configured:
        configured = get_settings().SECRET_KEY
    _SECRET_CACHE["secret"] = configured
    return configured


# ── Fingerprint helpers ────────────────────────────────────────────────────────

def _fingerprint(ip: str, user_agent: str) -> str:
    """
    Stable identity for the browser session. Same recipe the click-side fraud
    fingerprint uses (sha256 of ip:…), extended with the user agent so a
    same-IP different-device visitor cannot ride an authorization.
    """
    return hashlib.sha256(
        f"{ip or 'unknown'}:{(user_agent or '')[:500]}".encode()
    ).hexdigest()


def _slug_hash(slug: str) -> str:
    """Short non-reversible id for the slug the authorization is bound to."""
    return hashlib.sha256((slug or "").encode()).hexdigest()[:24]


def _session_key(token: str) -> str:
    return f"{_REDIS_PREFIX}{token}"


def _fp_key(fingerprint: str) -> str:
    return f"{_FP_PREFIX}{fingerprint}"


def _sh_key(slug_hash: str) -> str:
    return f"{_SH_PREFIX}{slug_hash}"


# ── Session record ─────────────────────────────────────────────────────────────

# Authorization lifecycle status.
STATUS_ACTIVE = "active"
STATUS_CONSUMED = "consumed"
STATUS_REVOKED = "revoked"


@dataclass
class AuthorizationSession:
    """
    One authorized click's prelander access session (STEP 2 record).

    The record holds the full internal routing context — publisher, campaign,
    offer, prelander, chain, OS/device, country, click, attribution — NONE of
    which ever reaches the visible URL. The externally visible handle is only
    the high-entropy random `token`; the record itself lives server-side in
    Redis and is looked up by token / fingerprint / slug hash.
    """
    # High-entropy cryptographic session identifier — secrets.token_urlsafe,
    # never sequential, never a campaign/db id.
    token: str

    # Browser binding
    fingerprint: str
    user_agent: str = ""

    # Route binding — the slug the authorization covers (hashed).
    slug_hash: str = ""

    # ── Internal context (server-side only, never in the URL) ──────────────
    click_id: str = ""                 # existing click document id
    publisher_id: str = ""             # Smartlink attribution
    website_id: str = ""               # site param attribution when present
    campaign_id: str = ""              # resolved campaign
    offer_id: str = ""                 # matched offer (offer rules)
    prelander_id: str = ""             # selected prelander template
    prelander_host: str = ""           # selected prelander domain
    chain_id: str = ""                 # redirection chain when one matched
    os: str = ""                       # detected OS (slug's os param)
    device_type: str = ""              # detected device type
    country_code: str = ""             # detected country
    referrer: str = ""                 # attribution/tracking referrer

    # Lifecycle
    created_at: int = 0
    expires_at: int = 0
    status: str = STATUS_ACTIVE
    # Progression state — how many protected resolves this session has served.
    # The /d page may legitimately resolve twice (domain-type probe + data);
    # a sane ceiling stops an authorized visitor from hammering the endpoint.
    consumed_count: int = 0

    def to_json(self) -> dict:
        return {
            "v": 2,
            "tok": self.token,
            "fp": self.fingerprint,
            "ua": self.user_agent,
            "sh": self.slug_hash,
            "click_id": self.click_id,
            "pub": self.publisher_id,
            "site": self.website_id,
            "camp": self.campaign_id,
            "offer": self.offer_id,
            "pl_id": self.prelander_id,
            "ph": self.prelander_host,
            "chain": self.chain_id,
            "os": self.os,
            "dev": self.device_type,
            "cc": self.country_code,
            "ref": self.referrer,
            "ts": self.created_at,
            "exp": self.expires_at,
            "status": self.status,
            "used": self.consumed_count,
        }

    @classmethod
    def from_json(cls, raw: str) -> Optional["AuthorizationSession"]:
        try:
            d = json.loads(raw)
            return cls(
                token=d.get("tok", ""),
                fingerprint=d.get("fp", ""),
                user_agent=d.get("ua", ""),
                slug_hash=d.get("sh", ""),
                click_id=d.get("click_id", ""),
                publisher_id=d.get("pub", ""),
                website_id=d.get("site", ""),
                campaign_id=d.get("camp", ""),
                offer_id=d.get("offer", ""),
                prelander_id=d.get("pl_id", ""),
                prelander_host=d.get("ph", ""),
                chain_id=d.get("chain", ""),
                os=d.get("os", ""),
                device_type=d.get("dev", ""),
                country_code=d.get("cc", ""),
                referrer=d.get("ref", ""),
                created_at=int(d.get("ts") or 0),
                expires_at=int(d.get("exp") or 0),
                status=d.get("status", STATUS_ACTIVE),
                consumed_count=int(d.get("used") or 0),
            )
        except Exception:
            return None

    def is_expired(self, now: Optional[int] = None) -> bool:
        now = now if now is not None else int(time.time())
        return now > self.expires_at + SESSION_SKEW_SECONDS

    def is_usable(self, now: Optional[int] = None) -> bool:
        return self.status == STATUS_ACTIVE and not self.is_expired(now)


# Maximum protected resolves one session may serve before it must be
# re-authorized (a new click). Generous headroom over the real /d flow:
# domain-type probe + data resolve + a refresh or two.
MAX_CONSUMPTIONS = 20


def _new_token() -> str:
    """
    High-entropy session identifier: 32 bytes of CSPRNG output, url-safe.

    Never sequential, never derived from any campaign/db id — guessing is
    computationally infeasible (~2^256).
    """
    return secrets.token_urlsafe(32)


# ── Core API ──────────────────────────────────────────────────────────────────

async def create_authorization(
    click_id: str,
    slug: str,
    ip: str,
    user_agent: str,
    redis,
    prelander_host: str = "",
    *,
    publisher_id: str = "",
    website_id: str = "",
    campaign_id: str = "",
    offer_id: str = "",
    prelander_id: str = "",
    chain_id: str = "",
    os: str = "",
    device_type: str = "",
    country_code: str = "",
    referrer: str = "",
    ttl: Optional[int] = None,
) -> Optional[AuthorizationSession]:
    """
    Create the authorization session for one click, right after the pipeline
    has resolved the prelander destination (STEP 2 session birth).

    The session carries the FULL internal routing context — publisher, site,
    campaign, offer, prelander template, prelander host, chain, OS/device,
    country, referrer, click id — all server-side only. The single external
    handle is the high-entropy random token; nothing internal reaches the
    visible URL.

    Called from the redirect pipeline (stage_authorize_prelander) while the
    legitimate Smartlink /click request is being served. The slug is the one
    embedded in the destination /d/{slug} URL, so the authorization and the
    route are pinned to each other.

    Lifetime comes from configuration (PRELANDER_SESSION_TTL, default 300s),
    never a hardcoded constant at call sites.

    Multi-server safe: everything lives in the shared Redis (STEP 3 option 1
    — the platform's existing distributed store), so any instance behind the
    load balancer can validate.

    Failures are logged and return None: authorization must never break the
    redirect flow (the visitor always leaves with a URL).
    """
    if not click_id or not slug or redis is None:
        return None
    try:
        now = int(time.time())
        effective_ttl = int(ttl) if ttl and int(ttl) > 0 else _session_ttl()
        session = AuthorizationSession(
            token=_new_token(),
            fingerprint=_fingerprint(ip, user_agent),
            user_agent=(user_agent or "")[:500],
            slug_hash=_slug_hash(slug),
            click_id=str(click_id),
            publisher_id=str(publisher_id or ""),
            website_id=str(website_id or ""),
            campaign_id=str(campaign_id or ""),
            offer_id=str(offer_id or ""),
            prelander_id=str(prelander_id or ""),
            prelander_host=(prelander_host or ""),
            chain_id=str(chain_id or ""),
            os=(os or ""),
            device_type=(device_type or ""),
            country_code=(country_code or ""),
            referrer=(referrer or "")[:500],
            created_at=now,
            expires_at=now + effective_ttl,
            status=STATUS_ACTIVE,
            consumed_count=0,
        )
        payload = json.dumps(session.to_json())
        # Session record + two O(1) indexes, all expiring together. The
        # fingerprint index is keyed by the FULL (ip, ua) hash so the lookup
        # path stays constant-time at validation; the slug index pins the
        # route. The visitor's fingerprint maps to exactly one live session —
        # a repeat click overwrites the older entry, keeping the keyset
        # bounded by concurrent visitors, not by traffic volume.
        pipe = redis.pipeline()
        pipe.setex(_session_key(session.token), effective_ttl, payload)
        pipe.setex(_fp_key(session.fingerprint), effective_ttl, session.token)
        pipe.setex(_sh_key(session.slug_hash), effective_ttl, session.token)
        await pipe.execute()
        logger.info(
            "[PRELANDER-AUTH] Authorization created for click=%s (host=%s ttl=%ss)",
            click_id, prelander_host or "-", effective_ttl,
        )
        return session
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Failed to create authorization: %s", e)
        return None


async def get_session(token: str, redis) -> Optional[AuthorizationSession]:
    """Fetch one session by its high-entropy token; None when absent/corrupt."""
    if not token or redis is None:
        return None
    try:
        raw = await redis.get(_session_key(token))
        if not raw:
            return None
        return AuthorizationSession.from_json(raw)
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Session fetch error: %s", e)
        return None


async def _consume(session: AuthorizationSession, redis) -> None:
    """
    Record a protected-resolve use on the session (progression state).

    Consumes are bounded: over MAX_CONSUMPTIONS the status flips to consumed
    and the session stops authorizing — a replayed token hammers a dead
    handle. Best-effort only; a failed write never blocks a legitimate
    visitor (validation has already passed).
    """
    try:
        session.consumed_count += 1
        if session.consumed_count >= MAX_CONSUMPTIONS:
            session.status = STATUS_CONSUMED
        remaining = session.expires_at - int(time.time())
        if remaining > 0:
            await redis.setex(
                _session_key(session.token), remaining, json.dumps(session.to_json())
            )
    except Exception as e:
        logger.debug("[PRELANDER-AUTH] Consume write failed (non-fatal): %s", e)


def session_reference(token: str, ip: str, user_agent: str) -> str:
    """
    A signed reference for the visitor's cookie — `token.signature`.

    The token is the high-entropy random session identifier (never a db/click
    id). The signature is HMAC(secret, token|fingerprint) so a leaked/guessed
    token alone cannot mint a valid reference, and the reference cannot be
    replayed from a different browser (fingerprint check at parse time).
    """
    if not token:
        return ""
    msg = f"{token}|{_fingerprint(ip, user_agent)}"
    sig = hmac.new(_auth_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{token}.{sig}"


def parse_session_reference(reference: str, ip: str, user_agent: str) -> Optional[str]:
    """
    Verify a cookie reference and return the session token it names.

    Returns None when the reference is malformed or the signature does not
    match the requesting browser — an attacker holding a stolen reference
    without the originating browser cannot use it.
    """
    if not reference or "." not in reference:
        return None
    token, _, sig = reference.rpartition(".")
    if not token or not sig:
        return None
    msg = f"{token}|{_fingerprint(ip, user_agent)}"
    expected = hmac.new(_auth_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        return None
    return token


async def validate_authorization(
    slug: str,
    ip: str,
    user_agent: str,
    redis,
    cookie_reference: Optional[str] = None,
    consume: bool = True,
) -> Optional[AuthorizationSession]:
    """
    Server-side authorization decision — called BEFORE prelander data is built.

    Valid when the visitor carries an ACTIVE, unexpired session bound to this
    exact browser and this exact slug. Lookup paths (defense in depth):

      1. Cookie — the signed `token.signature` reference names the session.
      2. Fingerprint index — cross-domain reality: no cookie travels between
         unrelated domains, so the O(1) fingerprint index maps this exact
         (IP, UA) browser to its live session.
      3. Slug index — mobile IP rotation: the slug still names the session;
         the UA (stable half of the fingerprint) confirms the same browser.

    The slug-hash match pins the authorization to the route: an authorization
    gained for one slug cannot be replayed to view a different prelander's
    data. Status and consumption are enforced: consumed/revoked/expired
    sessions stop authorizing.

    On success the session is consumed (progression state) and returned so the
    caller can reuse its internal context (campaign/offer/prelander) instead
    of re-resolving it from the slug. On failure returns None — the caller
    then serves the neutral "not available" page, revealing nothing.
    """
    if not slug or redis is None:
        return None

    target_hash = _slug_hash(slug)
    visitor_fp = _fingerprint(ip, user_agent)
    now = int(time.time())

    async def _check(token: Optional[str], *, require_fingerprint: bool = True) -> Optional[AuthorizationSession]:
        """Fetch and verify the session named by token against browser+slug."""
        if not token:
            return None
        session = await get_session(token, redis)
        if session is None:
            return None
        if not session.is_usable(now):
            return None
        if session.slug_hash != target_hash:
            return None
        if require_fingerprint and session.fingerprint != visitor_fp:
            return None
        return session

    session: Optional[AuthorizationSession] = None

    # ── Path 1: signed cookie reference ────────────────────────────────────
    if cookie_reference:
        token = parse_session_reference(cookie_reference, ip, user_agent)
        session = await _check(token)
        if session:
            await _accept(session, redis, consume)
            return session

    # ── Path 2: fingerprint index (cross-domain, cookie-less reality) ────
    try:
        token = await redis.get(_fp_key(visitor_fp))
        session = await _check(token)
        if session:
            await _accept(session, redis, consume)
            return session
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Fingerprint-path validation error: %s", e)

    # ── Path 3: slug-hash index (rotating-IP edge case) ──────────────────
    # Same browser, new network hop: the UA must still match exactly — a
    # different browser sharing the URL cannot pass this path.
    try:
        token = await redis.get(_sh_key(target_hash))
        if token:
            session = await get_session(token, redis)
            if (
                session
                and session.is_usable(now)
                and session.slug_hash == target_hash
                and hmac.compare_digest(session.user_agent, (user_agent or "")[:500])
            ):
                await _accept(session, redis, consume)
                return session
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Slug-path validation error: %s", e)

    return None


async def _accept(session: AuthorizationSession, redis, consume: bool) -> None:
    """Mark a validated session as used (progression), best-effort."""
    if consume:
        await _consume(session, redis)


async def revoke_authorization(token: str, redis) -> bool:
    """
    Revoke a session immediately (e.g. fraud verdict arrives after routing).

    Deletes the session record and its indexes; the token becomes worthless
    at once across every server instance (shared Redis).
    """
    if not token or redis is None:
        return False
    try:
        await redis.delete(_session_key(token))
        return True
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Revoke failed: %s", e)
        return False