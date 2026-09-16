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


# ── STEP 16 — structured security events ────────────────────────────────────────
# One emitter, stable event names, no secrets: never the token, never the
# cookie reference, never the handoff value. Internal ids (click/publisher/
# campaign) appear in these SERVER-side security logs only — that is their
# documented purpose (abuse analysis); the normal request logs carry
# redacted paths instead (see redact_path_tokens).

AUDIT = logging.getLogger("ppc_network.security")


def _redact(secret: str, keep: int = 6) -> str:
    """Truncate a secret-ish value for logs — first chars only, never enough to replay."""
    s = (secret or "").strip()
    return f"{s[:keep]}…" if len(s) > keep else "-"


def _event(name: str, **fields) -> None:
    """Emit a structured security event: `event=name key=value …` (flat, greppable)."""
    parts = [f"event={name}"]
    for key, value in fields.items():
        if value is None or value == "":
            continue
        text = str(value)
        # Defense in depth: token-shaped fields never print raw, whatever the caller passed
        if key in ("token", "handoff", "reference", "cookie", "pl_session"):
            text = _redact(text)
        parts.append(f"{key}={text}")
    AUDIT.info(" ".join(parts))


def redact_path_tokens(path: str) -> str:
    """
    Redact one-time handoff tokens from logged URL paths (STEP 16).

    /prelander/_auth/{43-char-secret} → /prelander/_auth/{token}
    The request logger middleware calls this so handoff tokens never reach
    normal application logs — only the security audit log sees (redacted)
    authorization activity.
    """
    import re
    return re.sub(
        r"(/prelander/_auth/)[A-Za-z0-9_\-]{10,}",
        r"\1{token}",
        path or "",
    )


async def check_auth_rate_limit(ip: str, redis) -> bool:
    """
    STEP 15 — per-IP limiter for the token-guessing surfaces (handoff mint +
    exchange). Returns True when the caller is WITHIN the limit.

    Limit/window from config (PRELANDER_AUTH_RATE_LIMIT /
    PRELANDER_AUTH_RATE_WINDOW). Best-effort: a Redis failure never blocks
    legitimate visitors (fail-open on the limiter; the tokens themselves are
    256-bit CSPRNG — guessing is not a viable attack even at unlimited rate).
    """
    if redis is None or not ip:
        return True
    try:
        from app.config import get_settings
        settings = get_settings()
        limit = int(getattr(settings, "PRELANDER_AUTH_RATE_LIMIT", 30) or 30)
        window = int(getattr(settings, "PRELANDER_AUTH_RATE_WINDOW", 60) or 60)
        key = f"prelander_auth_rl:{ip}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window)
        return int(count) <= limit
    except Exception:
        return True

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
_REDIS_PREFIX = "prelander_auth:"     # token -> session JSON
_FP_PREFIX = "prelander_auth_fp:"    # fingerprint -> token (string)
_SH_PREFIX = "prelander_auth_sh:"    # slug-hash  -> token (string)
_HANDOFF_PREFIX = "prelander_handoff:"   # one-time handoff token -> session token
_PL_SESSION_PREFIX = "prelander_plsess:"  # prelander-domain browsing session id -> session token

# Cookie carrying the authorization reference. HttpOnly + SameSite=Lax.
COOKIE_NAME = "mpa_pla"
# Prelander-domain browsing-session cookie (set by the handoff exchange).
PL_SESSION_COOKIE = "mpa_pls"


def cookie_ttl_seconds() -> int:
    return _session_ttl() + SESSION_SKEW_SECONDS


def cookie_flags() -> dict:
    """
    STEP 13 — the one canonical cookie attribute set for both prelander
    cookies. HttpOnly is always on; Secure/SameSite come from config
    (PRELANDER_COOKIE_SECURE / PRELANDER_COOKIE_SAMESITE) so deployments
    behind plain HTTP (local testing) can relax them without code edits.
    """
    from app.config import get_settings
    settings = get_settings()
    secure = getattr(settings, "PRELANDER_COOKIE_SECURE", True)
    if isinstance(secure, str):
        secure = secure.strip().lower() not in ("false", "0", "no", "off")
    samesite = (getattr(settings, "PRELANDER_COOKIE_SAMESITE", "lax") or "lax").strip().lower()
    if samesite not in ("lax", "strict", "none"):
        samesite = "lax"
    return {"httponly": True, "secure": bool(secure), "samesite": samesite}


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


def _handoff_key(handoff_token: str) -> str:
    return f"{_HANDOFF_PREFIX}{handoff_token}"


def _pl_session_key(pl_session_id: str) -> str:
    return f"{_PL_SESSION_PREFIX}{pl_session_id}"


# ── STEP 12 — IP-usage policy ────────────────────────────────────────────────────
# IP is an anti-abuse SIGNAL, never the sole session identifier: carrier NAT,
# proxies, corporate networks, VPNs and mobile IP rotation make it unreliable
# as a primary key. The User-Agent is the primary browser binding; the IP check
# is risk-based and CONFIGURABLE:
#   strict  — fingerprint (IP+UA) must match exactly; a rotated IP fails
#              (highest strictness, most false denials on mobile)
#   relaxed — UA must match; an IP change only downgrades the validation path
#              (default — mobile NAT/VPN-safe, still UA-bound and slug-bound)
def _ip_mode() -> str:
    import os
    from app.config import get_settings
    raw = (os.getenv("PRELANDER_IP_MODE", "") or "").strip().lower()
    if raw in ("strict", "relaxed"):
        return raw
    configured = (getattr(get_settings(), "PRELANDER_IP_MODE", "") or "").strip().lower()
    if configured in ("strict", "relaxed"):
        return configured
    return "relaxed"


# ── Session record ─────────────────────────────────────────────────────────────

# Authorization lifecycle status (STEP 11 state machine).
#   active    — issued at click time; usable
#   consumed  — consumption ceiling reached; dead handle
#   revoked   — administratively/anti-fraud killed
STATUS_ACTIVE = "active"
STATUS_CONSUMED = "consumed"
STATUS_REVOKED = "revoked"

# Handoff lifecycle (STEP 11): issued → exchanged (→ the browsing session it
# minted carries the onward lifecycle; the handoff record itself dies at the
# atomic exchange).
HANDOFF_ISSUED = "issued"
HANDOFF_EXCHANGED = "exchanged"


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
        _event(
            "redirect_session_created",
            click_id=click_id, host=prelander_host or "-", ttl=effective_ttl,
            publisher_id=publisher_id or "-", campaign_id=campaign_id or "-",
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
        # Atomic progression (STEP 18 race fix): Redis INCR cannot lose a
        # concurrent use — the old read-modify-write JSON update could. The
        # counter rides the session TTL; only after the atomic read is the
        # JSON rewritten with the fresh count (and the consumed status over
        # the ceiling).
        remaining = session.expires_at - int(time.time())
        if remaining <= 0:
            return
        count_key = f"{_REDIS_PREFIX}uses:{session.token}"
        count = await redis.incr(count_key)
        if count == 1:
            await redis.expire(count_key, remaining)
        session.consumed_count = int(count)
        if session.consumed_count >= MAX_CONSUMPTIONS:
            session.status = STATUS_CONSUMED
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
    browser and this exact slug. Lookup paths (defense in depth):

      1. Cookie — the signed `token.signature` reference names the session.
      2. Fingerprint index — cross-domain reality: no cookie travels between
         unrelated domains, so the O(1) fingerprint index maps this exact
         (IP, UA) browser to its live session.
      3. Slug index — mobile IP rotation: the slug still names the session;
         the UA (stable half of the fingerprint) confirms the same browser.

    STEP 12 — IP policy (PRELANDER_IP_MODE, default relaxed):
      strict  — the full fingerprint (IP+UA) must match; a rotated IP fails
                paths 1-2 (path 3 still saves it only via exact UA).
      relaxed  — the UA is the browser binding; an IP change downgrades the
                visitor to the slug-index path, which still demands the
                exact UA. A DIFFERENT BROWSER never passes anywhere, and the
                slug binding pins the route either way.

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
    strict_ip = _ip_mode() == "strict"

    async def _check(
        token: Optional[str],
        *,
        require_fingerprint: bool = True,
    ) -> Optional[AuthorizationSession]:
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
        if require_fingerprint:
            # STEP 12: in relaxed mode the UA — not the IP — is the browser
            # binding. The fingerprint check still runs in strict mode.
            if strict_ip:
                if session.fingerprint != visitor_fp:
                    return None
            else:
                if not hmac.compare_digest(session.user_agent, (user_agent or "")[:500]):
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
    # different browser sharing the URL cannot pass this path. In STRICT IP
    # mode a rotated IP is denied here too (path 2 already demanded the full
    # fingerprint); in relaxed mode this is the mobile/VPN-safe fallback.
    try:
        token = await redis.get(_sh_key(target_hash))
        if token:
            session = await get_session(token, redis)
            if (
                session
                and session.is_usable(now)
                and session.slug_hash == target_hash
                and hmac.compare_digest(session.user_agent, (user_agent or "")[:500])
                and (not strict_ip or session.fingerprint == visitor_fp)
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
        _event("prelander_session_expired", token=token, reason="revoked")
        return True
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Revoke failed: %s", e)
        return False


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4 — CROSS-DOMAIN ONE-TIME HANDOFF + PRELANDER-DOMAIN BROWSING SESSION
# ═════════════════════════════════════════════════════════════════════════════
#
# Domain reality (audited): Anchor, Inter and Prelander are UNRELATED
# registrar domains. A cookie set on one is NEVER readable by another —
# that is a browser security guarantee, not a configuration option. The
# cross-domain authorization therefore travels in the SERVER-SIDE session
# (fingerprint + slug binding from STEPS 1-3) and, when the architecture
# wants a real prelander-domain cookie, via this ONE-TIME handoff:
#
#   Inter /d/{slug} page
#     → requests a handoff token (still on the Inter domain, authorized by
#       the fingerprint/slug binding)
#     → navigates to prelander/_auth/{handoff}
#     → bootstrap endpoint validates the handoff server-side, CONSUMES it
#       (single use — replay impossible), mints the prelander-domain
#       HttpOnly browsing-session cookie
#     → 302 to the clean prelander URL (token removed from the visible URL)
#
# Handoff token properties (spec): high-entropy, short-lived, single-use,
# opaque, unrelated to db ids, carries no campaign/publisher info, replay-
# protected by atomic consume. The browsing session it mints is deliberately
# SEPARATE (STEP 7): refreshes and back/forward ride the browsing session,
# never re-consume the handoff, and never create a new ad click.


def _handoff_ttl() -> int:
    """Handoff validity — short by design (env-overridable)."""
    import os
    raw = os.getenv("PRELANDER_HANDOFF_TTL", "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return 60  # seconds — just long enough for one redirect hop


def _bare_host(value: str) -> str:
    """Reduce any browser-supplied string to a bare lowercase hostname — no scheme, port, path, or query."""
    raw = (value or "").strip().lower()
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    # Drop path/query/fragment and any userinfo, then any port
    raw = raw.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    raw = raw.rsplit("@", 1)[-1]
    raw = raw.split(":", 1)[0]
    return raw.strip()


def resolve_handoff_target(session: AuthorizationSession, requested_host: str) -> Optional[str]:
    """
    STEP 14 — open-redirect protection for the handoff target.

    The destination is decided SERVER-SIDE: the session recorded the selected
    prelander host at click time (route_click's own pick). A browser-supplied
    ?target_host= is only honored when it matches that recorded host exactly;
    any other value (attacker.com, a different prelander, a URL with a path)
    means DENY (return None). When the session carries no recorded host
    (legacy pre-STEP-9 session) the browser value is reduced to a bare
    hostname — it can never smuggle in an arbitrary redirect URL.
    """
    session_host = _bare_host(getattr(session, "prelander_host", "") or "")
    requested = _bare_host(requested_host or "")
    if session_host:
        if requested and requested != session_host:
            return None
        return session_host
    return requested or ""


async def mint_handoff(
    session: AuthorizationSession,
    redis,
    target_host: str = "",
    ttl: Optional[int] = None,
) -> Optional[str]:
    """
    Mint a one-time handoff token for an already-authorized session.

    The token is pure CSPRNG output — it carries no campaign, publisher, or
    any internal id. It maps (in Redis) to the session token + the target
    prelander host, and dies with the atomic consume below.
    """
    if redis is None or session is None or not session.is_usable():
        return None
    try:
        effective_ttl = int(ttl) if ttl and int(ttl) > 0 else _handoff_ttl()
        handoff_token = secrets.token_urlsafe(32)
        value = json.dumps({
            "st": session.token,
            "th": (target_host or ""),
            # STEP 11 lifecycle: issued → exchanged (at consume). The atomic
            # GETDEL below is the actual single-use guard; this field is the
            # auditable state trail.
            "state": HANDOFF_ISSUED,
        })
        await redis.setex(_handoff_key(handoff_token), effective_ttl, value)
        _event(
            "handoff_token_created",
            click_id=session.click_id, target=target_host or "-", ttl=effective_ttl,
        )
        return handoff_token
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Handoff mint failed: %s", e)
        return None


async def consume_handoff(
    handoff_token: str,
    redis,
    requesting_host: str = "",
    ip: str = "",
    user_agent: str = "",
) -> Optional[AuthorizationSession]:
    """
    Atomically exchange a one-time handoff for its authorization session.

    Single-use: the GET+DELETE race is closed by deleting FIRST — only one
    concurrent caller ever wins the value; every other attempt (replay,
    double-click, shared URL) sees nothing. Returns the bound session only
    when it is still usable and the exchange happens on the expected target
    host (when the handoff was minted with one) from the expected browser.
    """
    if not handoff_token or redis is None:
        return None
    try:
        # STEP 11 — atomic single-use consume: GETDEL deletes FIRST, so exactly
        # one concurrent caller can win the value; every later attempt (replay,
        # double-click, back button, shared URL) sees nothing.
        raw = await redis.getdel(_handoff_key(handoff_token))
        if not raw:
            _event("replay_attempt_detected", token=handoff_token)
            logger.info("[PRELANDER-AUTH] Handoff replay/unknown token denied")
            return None
        payload = json.loads(raw)
        session_token = payload.get("st", "")
        target = payload.get("th", "")

        if target and requesting_host and target != requesting_host:
            _event("invalid_domain_access", host=requesting_host, expected=target)
            logger.warning(
                "[PRELANDER-AUTH] Handoff host mismatch (want=%s got=%s)", target, requesting_host,
            )
            return None

        session = await get_session(session_token, redis)
        if session is None or not session.is_usable():
            _event("prelander_session_expired", click_id=getattr(session, "click_id", "") or "-", reason="expired_or_revoked")
            return None
        # STEP 12 — browser binding: the UA must match (IP is a signal, and
        # in relaxed mode a mid-flow IP rotation is legitimate). A different
        # browser on the same IP never passes.
        if ip:
            if session.fingerprint != _fingerprint(ip, user_agent):
                if not hmac.compare_digest(session.user_agent, (user_agent or "")[:500]):
                    _event("handoff_exchange_denied", reason="browser_mismatch", click_id=session.click_id)
                    logger.info("[PRELANDER-AUTH] Handoff exchanged from a different browser — denied")
                    return None
        # state trail: the handoff record is already deleted (atomic); the
        # exchange is logged so the lifecycle is auditable.
        _event("handoff_token_exchanged", click_id=session.click_id, host=requesting_host or "-")
        logger.info(
            "[PRELANDER-AUTH] Handoff exchanged (state=%s click=%s)",
            HANDOFF_EXCHANGED, session.click_id,
        )
        return session
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Handoff consume failed: %s", e)
        return None


async def establish_prelander_session(
    session: AuthorizationSession,
    redis,
) -> Optional[str]:
    """
    Establish the prelander-domain BROWSING session (STEP 7 part B).

    Separate from the one-time handoff on purpose: after this exchange the
    visitor's refreshes, back/forward and asset loads ride this id. Refresh
    never re-consumes the handoff, never creates a click, never mints a new
    authorization — the browsing session just gets looked up again.
    """
    if redis is None or session is None:
        return None
    try:
        pl_session_id = secrets.token_urlsafe(32)
        # The browsing session lives as long as the click authorization it
        # derives from — no independent lifetime that could outlive it.
        remaining = max(session.expires_at - int(time.time()), 1)
        await redis.setex(_pl_session_key(pl_session_id), remaining, session.token)
        _event("prelander_session_created", click_id=session.click_id, ttl=remaining)
        return pl_session_id
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Prelander session establish failed: %s", e)
        return None


async def validate_prelander_session(
    pl_session_id: str,
    redis,
    slug: str = "",
) -> Optional[AuthorizationSession]:
    """
    Resolve a prelander-domain browsing-session id back to its authorization.

    Returns None when the id is unknown/expired, when the underlying click
    authorization died (revoked/consumed/expired), or — when a slug is given —
    when the authorization is not bound to that slug (route pinning).
    """
    if not pl_session_id or redis is None:
        return None
    try:
        session_token = await redis.get(_pl_session_key(pl_session_id))
        if not session_token:
            return None
        session = await get_session(session_token, redis)
        if session is None or not session.is_usable():
            return None
        if slug and session.slug_hash != _slug_hash(slug):
            return None
        return session
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Prelander session validation failed: %s", e)
        return None


# ═════════════════════════════════════════════════════════════════════════════
# STEP 5 — PRELANDER ACCESS MIDDLEWARE (validation orchestrator)
# ═════════════════════════════════════════════════════════════════════════════

async def validate_prelander_access(
    *,
    slug: str,
    ip: str,
    user_agent: str,
    redis,
    db,
    request_host: str = "",
    cookie_reference: Optional[str] = None,
    pl_session_cookie: Optional[str] = None,
    expected_campaign_id: Optional[str] = None,
    expected_prelander_host: Optional[str] = None,
    consume: bool = True,
) -> Optional[AuthorizationSession]:
    """
    The single place every protected-prelander request must pass through
    (STEP 5). Implements the full checklist BEFORE any protected HTML/data:

      1.  session exists          — some binding names a stored session
      2.  cryptographically valid — cookie reference signature verifies
      3.  not expired            — expires_at honored (+ small skew)
      4.  belongs to this browser— fingerprint (IP+UA) / UA match
      5.  matches this domain     — session.prelander_host == request host
      6.  maps to the campaign    — resolved campaign id == session.campaign_id
      7.  maps to the prelander   — slug binding == THIS route's slug
      8.  not revoked             — status must be active
      9.  not replayed            — consumption ceiling intact
      10. click/session exists    — session.click_id still resolvable
      11. handoff single-use      — handled by consume_handoff (getdel);
                                     the browsing session here is the
                                     post-exchange artifact, so replays of the
                                     handoff token are already impossible

    Returns the session on success (the caller renders), None on any failure
    (the caller serves the STEP 6 denied fallback — never more, never less).
    Every failure logs the check that failed, never the protected contents.
    """
    if redis is None:
        logger.error("[PRELANDER-AUTH] No Redis for validation — denying")
        return None

    now = int(time.time())
    session: Optional[AuthorizationSession] = None
    source = ""

    # ── 1/2/3/8/9: obtain a stored, signature-valid, usable session ───────
    # Prelander-domain browsing session first (STEP 7 part B): refreshes and
    # back/forward land here and must NOT re-consume anything.
    if pl_session_cookie:
        session = await validate_prelander_session(pl_session_cookie, redis, slug=slug)
        if session:
            source = "pl_session"

    if session is None:
        session = await validate_authorization(
            slug=slug, ip=ip, user_agent=user_agent, redis=redis,
            cookie_reference=cookie_reference, consume=consume,
        )
        if session:
            source = "binding"

    if session is None:
        _event("prelander_access_denied", slug=(slug or "")[:10] + "…")
        logger.info("[PRELANDER-AUTH] Check 1-4 failed: no usable session (slug=%s…)", (slug or "")[:10])
        return None

    # ── 4 (browser ownership) is enforced by validate_authorization's
    #    fingerprint match; the browsing session id is itself HttpOnly and
    #    was minted server-side, so possession proves the exchange happened.

    # ── 5: the authorization must match the prelander domain being asked for.
    if (
        expected_prelander_host
        and session.prelander_host
        and expected_prelander_host != session.prelander_host
    ):
        _event("invalid_domain_access", host=expected_prelander_host, expected=session.prelander_host)
        logger.info(
            "[PRELANDER-AUTH] Check 5 failed: host mismatch (session=%s request=%s)",
            session.prelander_host, expected_prelander_host,
        )
        return None

    # ── 6: the authorization must map to the campaign this request resolves.
    if expected_campaign_id and session.campaign_id and str(expected_campaign_id) != session.campaign_id:
        _event("invalid_campaign_binding", campaign=expected_campaign_id, expected=session.campaign_id)
        logger.info(
            "[PRELANDER-AUTH] Check 6 failed: campaign mismatch (session=%s request=%s)",
            session.campaign_id, expected_campaign_id,
        )
        return None

    # ── 10: the click the authorization references must still exist.
    if session.click_id and db is not None:
        try:
            from bson import ObjectId
            oid = ObjectId(session.click_id) if ObjectId.is_valid(session.click_id) else session.click_id
            click = await db.clicks.find_one({"_id": oid}, {"_id": 1})
            if not click:
                _event("prelander_access_denied", click_id=session.click_id, reason="click_gone")
                logger.info("[PRELANDER-AUTH] Check 10 failed: click %s gone", session.click_id)
                return None
        except Exception as e:
            # A transient DB error must not deny a fully-authorized visitor.
            logger.debug("[PRELANDER-AUTH] Click existence check skipped: %s", e)

    _event(
        "prelander_access_allowed",
        click_id=session.click_id or "-", host=expected_prelander_host or "-",
        source=source,
    )
    logger.info(
        "[PRELANDER-AUTH] Access granted via %s (click=%s host=%s)",
        source, session.click_id or "-", expected_prelander_host or "-",
    )
    return session


# ═════════════════════════════════════════════════════════════════════════════
# STEP 6 — CONFIGURABLE SAFE FALLBACK FOR DENIED ACCESS
# ═════════════════════════════════════════════════════════════════════════════

_DENIED_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Page Not Found</title>
<style>
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:#f0f2f5; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
  .box {{ text-align:center; }}
  .icon {{ width:64px; height:64px; border-radius:50%; background:#e5e7eb; margin:0 auto 16px;
           display:flex; align-items:center; justify-content:center; }}
  p {{ color:#6b7280; font-size:14px; }}
</style>
</head>
<body>
  <div class="box">
    <div class="icon">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="2">
        <path d="M12 15V9m0 0v6m-6-6h12" stroke-linecap="round" stroke-linejoin="round" opacity="0"/>
        <path d="M12 15V9" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M12 15V9.5" stroke-linecap="round" stroke-linejoin="round" opacity="0"/>
        <path d="M15 9h-6" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <p>This link is no longer available.</p>
  </div>
</body>
</html>"""


def build_denied_response(redis=None):
    """
    The configurable safe fallback for denied prelander access (STEP 6).

    Mode (PRELANDER_DENIED_MODE): generic_page (default) | not_found |
    forbidden | redirect. Never leaks campaign/publisher/internal info, never
    a stack trace — the same neutral response whatever the failure was.
    """
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
    from app.config import get_settings

    mode = (getattr(get_settings(), "PRELANDER_DENIED_MODE", "generic_page") or "generic_page").strip().lower()

    if mode == "not_found":
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    if mode == "forbidden":
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    if mode == "redirect":
        target = (getattr(get_settings(), "PRELANDER_DENIED_FALLBACK_URL", "") or "").strip()
        if target.startswith(("http://", "https://")):
            return RedirectResponse(url=target, status_code=302)
        # Misconfigured redirect target — fall through to the generic page
        # rather than 302-ing somewhere unsafe.
    return HTMLResponse(content=_DENIED_PAGE, status_code=404)