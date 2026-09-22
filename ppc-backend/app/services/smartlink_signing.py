"""
Smartlink signing service
=========================
Cryptographically secure hash generation and server-side validation for
Smart Links / Anchor Links.

Compatibility helpers for previously issued signed Smartlinks. New links use
only publisher/website IDs by default. Existing HMAC-SHA256 tokens remain bound
to the exact Tag ID(s) they name:

    https://anchor.com/click?pub=PUB_XXXXXXXX&site=SITE_XXXXXXXX&hmac=<hex>

Binding model:
  - The token is HMAC(secret, "v1|pub|site") — changing ONE character of the
    tag values, or moving a token to a different link, breaks the MAC.
  - The secret is the platform's REDIRECT_SECRET_KEY (falling back to
    SECRET_KEY) — never exposed in URLs, responses, or logs.
  - Nonce support: a per-link random `n` parameter can be folded into the
    signed message so no two generated links are byte-identical, while every
    copy of one link still validates.

Validation (click time):
  - `verify_smartlink_token` recomputes the HMAC from the request's own pub/
    site values and compares in constant time. Tampered hashes, arbitrary
    tokens, and hash/param swaps are rejected with 403.
  - Legacy links without a token keep working (the click pipeline predates
    signing); enforcing rejection for token-less links is a config flag
    (SMARTLINK_HASH_REQUIRED) for deployments that want strict mode.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import Optional

logger = logging.getLogger(__name__)

# Token version prefix — lets the MAC message format evolve without old links
# silently validating against a new recipe.
_TOKEN_VERSION = "v1"

_SECRET_CACHE: dict = {"secret": None}


def _signing_secret() -> str:
    """
    HMAC key for smartlink signatures. Reuses REDIRECT_SECRET_KEY (the same
    policy as the prelander authorization service) — no new secret to provision.
    """
    cached = _SECRET_CACHE.get("secret")
    if cached:
        return cached
    import os
    from app.config import get_settings
    settings = get_settings()
    configured = (settings.REDIRECT_SECRET_KEY or "").strip()
    if not configured:
        configured = os.getenv("REDIRECT_SECRET_KEY", "").strip()
    if not configured:
        configured = (settings.SECRET_KEY or "").strip()
    _SECRET_CACHE["secret"] = configured
    return configured


def _message(pub: str, site: Optional[str], nonce: str = "") -> str:
    """The exact bytes a token binds to. `site` may be empty (manual pubs)."""
    return f"{_TOKEN_VERSION}|{pub or ''}|{site or ''}|{nonce or ''}"


def generate_link_token(pub: str, site: Optional[str] = None, nonce: str = "") -> str:
    """
    System-generated cryptographic hash for one Smartlink.

    32 hex chars of HMAC-SHA256 over (version, pub, site, nonce) — unique per
    link, unforgable without the server secret, and bound to the exact Tag
    ID(s): a token from another link (or for a modified pub/site) fails.
    """
    secret = _signing_secret()
    if not secret or not pub:
        return ""
    msg = _message(pub, site, nonce)
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]


def verify_link_token(pub: str, site: Optional[str], token: str, nonce: str = "") -> bool:
    """
    Server-side validation of a Smartlink token (constant-time).

    Returns True only when `token` is exactly the HMAC this system would
    generate for the REQUEST's pub/site values — a modified hash, an arbitrary
    token, or a valid token swapped onto different parameters all fail.
    """
    if not token or not pub:
        return False
    expected = generate_link_token(pub, site, nonce)
    if not expected:
        # No secret configured — validation is impossible; fail CLOSED when a
        # token was supplied (do not reward guessing with a pass).
        return False
    return hmac.compare_digest(expected, token.strip().lower())


def new_link_nonce() -> str:
    """
    Fresh CSPRNG nonce for per-link uniqueness: each generated Smartlink gets
    its own `n` value, so two links to the same publisher/site carry different
    (but each individually valid) tokens.
    """
    return secrets.token_hex(8)


def hash_required() -> bool:
    """Strict mode flag (SMARTLINK_HASH_REQUIRED, default false = legacy links keep working)."""
    import os
    raw = (os.getenv("SMARTLINK_HASH_REQUIRED", "") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    try:
        from app.config import get_settings
        return bool(getattr(get_settings(), "SMARTLINK_HASH_REQUIRED", False))
    except Exception:
        return False


def signed_link_params(pub: str, site: Optional[str] = None, nonce: Optional[str] = None) -> dict:
    """
    The complete parameter set for a signed Smartlink: the ids the caller
    already has + the system-generated token (and its nonce when one was used).
    Callers merge this over their structure-driven params.

    When no nonce is passed, one is generated — the whole point is that every
    generated link carries its own nonce so no two links are byte-identical.
    """
    n = nonce if nonce is not None else new_link_nonce()
    token = generate_link_token(pub, site, n)
    params = {"hmac": token}
    if n:
        params["n"] = n
    return params
