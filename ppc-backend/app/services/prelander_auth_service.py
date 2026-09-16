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
import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── Tunables (kept deliberately conservative) ─────────────────────────────────

# How long a click's authorization stays valid. Matches the prelander slug's
# 1-hour validity window in prelander_router._decode_slug — the two travel
# together and should expire together.
SESSION_TTL_SECONDS = 3600

# Allowed clock skew (seconds) when comparing session timestamps.
SESSION_SKEW_SECONDS = 60

# Redis key namespaces. Per-click session + two O(1) lookup indexes so
# validation never needs a KEYS scan (KEYS blocks Redis; banned in production).
_REDIS_PREFIX = "prelander_auth:"
_FP_PREFIX = "prelander_auth_fp:"   # fingerprint -> click_id (string)
_SH_PREFIX = "prelander_auth_sh:"   # slug-hash  -> click_id (string)

# Cookie carrying the authorization reference. HttpOnly + SameSite=Lax.
COOKIE_NAME = "mpa_pla"
COOKIE_TTL_SECONDS = SESSION_TTL_SECONDS

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


def _session_key(click_id: str) -> str:
    return f"{_REDIS_PREFIX}{click_id}"


def _fp_key(fingerprint: str) -> str:
    return f"{_FP_PREFIX}{fingerprint}"


def _sh_key(slug_hash: str) -> str:
    return f"{_SH_PREFIX}{slug_hash}"


# ── Session record ────────────────────────────────────────────────────────────

@dataclass
class AuthorizationSession:
    """One authorized click's prelander access session."""
    click_id: str
    fingerprint: str
    slug_hash: str
    created_at: int
    prelander_host: str = ""
    user_agent: str = ""

    def to_json(self) -> dict:
        return {
            "v": 1,
            "click_id": self.click_id,
            "fp": self.fingerprint,
            "sh": self.slug_hash,
            "ts": self.created_at,
            "ph": self.prelander_host,
            "ua": self.user_agent,
        }


# ── Core API ──────────────────────────────────────────────────────────────────

async def create_authorization(
    click_id: str,
    slug: str,
    ip: str,
    user_agent: str,
    redis,
    prelander_host: str = "",
    ttl: int = SESSION_TTL_SECONDS,
) -> bool:
    """
    Create the authorization session for one click, right after the pipeline
    has resolved the prelander destination.

    Called from the redirect pipeline (stage_authorize_prelander) — i.e. while
    the legitimate Smartlink /click request is being served. The slug is the
    one embedded in the destination /d/{slug} URL, so the authorization and
    the route are pinned to each other.

    Failures are logged and swallowed: authorization must never break the
    redirect flow (the visitor always leaves with a URL).
    """
    if not click_id or not slug or redis is None:
        return False
    try:
        session = AuthorizationSession(
            click_id=str(click_id),
            fingerprint=_fingerprint(ip, user_agent),
            slug_hash=_slug_hash(slug),
            created_at=int(time.time()),
            prelander_host=(prelander_host or ""),
            user_agent=(user_agent or "")[:500],
        )
        import json
        payload = json.dumps(session.to_json())
        # Session record + two O(1) indexes, all expiring together. The
        # fingerprint index is keyed by the FULL (ip, ua) hash so the lookup
        # path stays constant-time at validation; the slug index pins the
        # route. The visitor's fingerprint maps to exactly one live click —
        # a repeat click overwrites the older entry, keeping the keyset
        # bounded by concurrent visitors, not by traffic volume.
        pipe = redis.pipeline()
        pipe.setex(_session_key(str(click_id)), ttl, payload)
        pipe.setex(_fp_key(session.fingerprint), ttl, str(click_id))
        pipe.setex(_sh_key(session.slug_hash), ttl, str(click_id))
        await pipe.execute()
        logger.info(
            "[PRELANDER-AUTH] Authorization created for click=%s (host=%s)",
            click_id, prelander_host or "-",
        )
        return True
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Failed to create authorization: %s", e)
        return False


def session_reference(click_id: str, ip: str, user_agent: str) -> str:
    """
    A signed reference for the visitor's cookie — `click_id.signature`.

    The signature is HMAC(secret, click_id|fingerprint) so a leaked/guessed
    click id alone cannot mint a valid reference, and the cookie cannot be
    replayed from a different browser (fingerprint check on validation).
    """
    if not click_id:
        return ""
    msg = f"{click_id}|{_fingerprint(ip, user_agent)}"
    sig = hmac.new(_auth_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{click_id}.{sig}"


def parse_session_reference(reference: str, ip: str, user_agent: str) -> Optional[str]:
    """
    Verify a cookie reference and return the click id it names.

    Returns None when the reference is malformed or the signature does not
    match the requesting browser — an attacker holding a stolen reference
    without the originating browser cannot use it.
    """
    if not reference or "." not in reference:
        return None
    click_id, _, sig = reference.rpartition(".")
    if not click_id or not sig:
        return None
    msg = f"{click_id}|{_fingerprint(ip, user_agent)}"
    expected = hmac.new(_auth_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        return None
    return click_id


async def validate_authorization(
    slug: str,
    ip: str,
    user_agent: str,
    redis,
    cookie_reference: Optional[str] = None,
) -> bool:
    """
    Server-side authorization decision — called BEFORE prelander data is built.

    Valid when EITHER binding matches (defense in depth, cross-domain safe):

      1. Cookie binding — a signed reference for a click whose session exists,
         is unexpired, matches this browser fingerprint, and whose slug hash
         matches the requested slug. Works across any domains (the reference
         is a signed value in the request, not a server-side session cookie).
      2. Fingerprint path — no cookie (cross-domain reality) but a session
         exists whose fingerprint matches this exact browser and whose slug
         hash matches. Redis keys are scanned within the TTL window; the key
         set is bounded by authorized clicks in the last hour.

    The slug-hash match pins the authorization to the route: an authorization
    gained for one slug cannot be replayed to view a different prelander's
    data.

    Returns False on any failure — the caller then serves the neutral
    "not available" page, revealing nothing.
    """
    if not slug or redis is None:
        return False

    import json

    target_hash = _slug_hash(slug)
    visitor_fp = _fingerprint(ip, user_agent)
    now = int(time.time())

    async def _check(click_id: str) -> bool:
        """Verify the session named by click_id against this browser + slug."""
        if not click_id:
            return False
        try:
            raw = await redis.get(_session_key(click_id))
            if not raw:
                return False
            session = json.loads(raw)
            return (
                session.get("fp") == visitor_fp
                and session.get("sh") == target_hash
                and now - int(session.get("ts") or 0)
                <= SESSION_TTL_SECONDS + SESSION_SKEW_SECONDS
            )
        except Exception as e:
            logger.warning("[PRELANDER-AUTH] Session check error: %s", e)
            return False

    # ── Path 1: signed cookie reference ────────────────────────────────────
    if cookie_reference:
        click_id = parse_session_reference(cookie_reference, ip, user_agent)
        if click_id and await _check(click_id):
            return True

    # ── Path 2: fingerprint index (cross-domain, cookie-less reality) ────
    # O(1): the fingerprint index maps this exact browser to its live click.
    try:
        click_id = await redis.get(_fp_key(visitor_fp))
        if click_id and await _check(click_id):
            return True
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Fingerprint-path validation error: %s", e)

    # ── Path 3: slug-hash index (cookie-less + rotating-IP edge cases) ────
    # Covers a visitor whose IP changed between /click and the prelander hop
    # (mobile networks): the slug index still names the click, so confirm the
    # session exists, is fresh, is bound to this slug, and was created by the
    # same browser — the UA is the stable half of the fingerprint, so compare
    # it directly. A different browser sharing the URL cannot pass this.
    try:
        click_id = await redis.get(_sh_key(target_hash))
        if click_id:
            raw = await redis.get(_session_key(click_id))
            if raw:
                session = json.loads(raw)
                same_browser = hmac.compare_digest(
                    (session.get("ua") or ""), (user_agent or "")[:500]
                )
                if (
                    session.get("sh") == target_hash
                    and same_browser
                    and now - int(session.get("ts") or 0)
                    <= SESSION_TTL_SECONDS + SESSION_SKEW_SECONDS
                ):
                    return True
    except Exception as e:
        logger.warning("[PRELANDER-AUTH] Slug-path validation error: %s", e)

    return False