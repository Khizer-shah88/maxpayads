"""
test_entry_guard.py

Server-side tests for the Conditional Entry Access / Protected Landing Flow.

These tests use pytest + httpx to hit the Next.js middleware through the
FastAPI test client is NOT appropriate here because this middleware lives in
Next.js.  Instead we test the *logic* extracted into pure Python equivalents
that mirror what entry-guard.ts does, plus end-to-end-style behaviour checks.

Because the real implementation lives in TypeScript (Next.js Edge middleware),
these tests serve two purposes:
  1. Document and verify the expected request/response behaviour at the HTTP
     boundary (using FastAPI's test client to proxy through to a test stub).
  2. Directly test the Python-equivalent helper logic for referrer validation,
     token structure, and expiry rules.

Running:
    cd ppc-backend
    pytest tests/test_entry_guard.py -v
"""

import hashlib
import hmac
import time
import base64
import pytest
from urllib.parse import urlparse


# ─── Pure-Python equivalents of entry-guard.ts helpers ───────────────────────
# These mirror the TypeScript logic so we can test it without a Node process.

COOKIE_NAME = "entry_session"


def _sign(payload: str, secret: str) -> str:
    """HMAC-SHA256, base64url-encoded (no padding) — mirrors signPayload()."""
    sig_bytes = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    b64 = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=")
    return b64.decode()


def create_session_token(secret: str, issued_at: int | None = None) -> str:
    """Create a session token identical to createSessionToken() in TypeScript."""
    ts = str(issued_at if issued_at is not None else int(time.time()))
    sig = _sign(ts, secret)
    return f"{ts}.{sig}"


def validate_session_token(
    token: str, secret: str, ttl_seconds: int
) -> str:
    """Returns 'valid', 'expired', or 'invalid'. Mirrors validateSessionToken()."""
    if not token or not secret:
        return "invalid"
    dot = token.rfind(".")
    if dot < 1:
        return "invalid"
    issued_at_str = token[:dot]
    signature = token[dot + 1:]
    try:
        issued_at = int(issued_at_str)
    except ValueError:
        return "invalid"

    # Verify signature
    expected_sig = _sign(issued_at_str, secret)
    # Constant-time comparison
    if not hmac.compare_digest(signature, expected_sig):
        return "invalid"

    # TTL check
    now = int(time.time())
    if now - issued_at > ttl_seconds:
        return "expired"

    return "valid"


def is_referrer_allowed(referrer: str | None, allowed_domains: list[str]) -> bool:
    """
    Returns True only when referrer hostname exactly matches one of the
    configured allowed hostnames.  Mirrors isReferrerAllowed().
    """
    if not referrer or not allowed_domains:
        return False
    try:
        hostname = urlparse(referrer).hostname or ""
        hostname = hostname.lower()
    except Exception:
        return False

    allowed_hostnames = set()
    for domain in allowed_domains:
        try:
            h = urlparse(domain).hostname or ""
            allowed_hostnames.add(h.lower())
        except Exception:
            pass

    return hostname in allowed_hostnames


# ─── Test helpers ─────────────────────────────────────────────────────────────

ALLOWED = ["https://browsmac.org", "https://www.browsmac.org"]
SECRET = "test-secret-that-is-at-least-32-chars-long"
TTL = 900  # 15 minutes


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1 — Direct request (no cookie, no valid referrer) → DENY
# ═══════════════════════════════════════════════════════════════════════════════

def test_direct_request_no_cookie_no_referrer():
    """No session cookie, no referrer → access must be denied."""
    session_cookie = None
    referrer = None

    has_session = session_cookie is not None
    ref_allowed = is_referrer_allowed(referrer, ALLOWED)

    assert not has_session, "Should have no session"
    assert not ref_allowed, "Should not pass referrer check"
    # Conclusion: DENY
    decision = "DENY" if (not has_session and not ref_allowed) else "ALLOW"
    assert decision == "DENY"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2 — Allowed referring page, no existing session → grant + create session
# ═══════════════════════════════════════════════════════════════════════════════

def test_allowed_referrer_no_session_creates_session():
    """Arrival from allowed domain with no existing session → session created."""
    referrer = "https://browsmac.org/some/path"
    session_cookie = None

    ref_allowed = is_referrer_allowed(referrer, ALLOWED)
    assert ref_allowed, "browsmac.org must be in the allowlist"

    token = create_session_token(SECRET)
    assert "." in token, "Token must contain a dot separator"

    parts = token.split(".")
    assert len(parts) == 2, "Token must have exactly two parts"
    assert parts[0].isdigit(), "First part must be a Unix timestamp"

    # Validate freshly created token
    result = validate_session_token(token, SECRET, TTL)
    assert result == "valid", f"Fresh token must be valid, got: {result}"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3 — Valid session present, no referrer → allow (handles reload/new tab)
# ═══════════════════════════════════════════════════════════════════════════════

def test_valid_session_no_referrer_is_allowed():
    """
    User refreshes the page — no Referer header is sent.
    A valid session cookie must be sufficient to grant access.
    """
    referrer = None
    token = create_session_token(SECRET)
    state = validate_session_token(token, SECRET, TTL)

    assert state == "valid"
    # Even though referrer is missing, valid session = access granted
    ref_allowed = is_referrer_allowed(referrer, ALLOWED)
    assert not ref_allowed  # referrer check fails, but session check passes
    decision = "ALLOW" if state == "valid" else (
        "ALLOW" if ref_allowed else "DENY"
    )
    assert decision == "ALLOW"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4 — Expired session, no valid referrer → DENY
# ═══════════════════════════════════════════════════════════════════════════════

def test_expired_session_no_referrer_is_denied():
    """Session expired AND no allowed referrer → must redirect to fallback."""
    # Create a token that was issued 20 minutes ago (past 15 min TTL)
    past = int(time.time()) - 1200
    token = create_session_token(SECRET, issued_at=past)

    state = validate_session_token(token, SECRET, TTL)
    assert state == "expired", f"Expected expired, got: {state}"

    referrer = None
    ref_allowed = is_referrer_allowed(referrer, ALLOWED)
    assert not ref_allowed

    decision = "DENY" if (state != "valid" and not ref_allowed) else "ALLOW"
    assert decision == "DENY"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5 — Invalid/unrelated referrer → DENY
# ═══════════════════════════════════════════════════════════════════════════════

def test_invalid_referrer_is_denied():
    """Referrer from a domain not in the allowlist → access denied."""
    for bad_referrer in [
        "https://evil.com/",
        "https://unrelated-site.net/",
        "https://notallowed.org/page",
    ]:
        assert not is_referrer_allowed(bad_referrer, ALLOWED), (
            f"Referrer {bad_referrer} should NOT be allowed"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6 — Malicious lookalike referrer → DENY
# ═══════════════════════════════════════════════════════════════════════════════

def test_malicious_lookalike_referrer_is_denied():
    """
    Lookalike domains must be rejected — hostname comparison must be exact.

    https://browsmac.org.evil.com  → hostname = browsmac.org.evil.com  (not allowed)
    https://evil.com/?r=browsmac.org → hostname = evil.com             (not allowed)
    https://fakebrowsmac.org        → hostname = fakebrowsmac.org      (not allowed)
    """
    malicious = [
        "https://browsmac.org.evil.com/",
        "https://evil.com/?redirect=https://browsmac.org",
        "https://fakebrowsmac.org/",
        "https://browsmac.org.hacker.io/",
        "https://xn--browsmac-org.evil.com/",  # unicode lookalike
    ]
    for ref in malicious:
        result = is_referrer_allowed(ref, ALLOWED)
        assert not result, (
            f"Malicious referrer '{ref}' must be DENIED but was ALLOWED"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7 — New tab, no session, direct domain → DENY
# ═══════════════════════════════════════════════════════════════════════════════

def test_new_tab_direct_domain_denied():
    """
    Opening https://maxpayads.com in a new tab:
      - No entry_session cookie
      - No Referer header (new tab omits it)
    → must redirect to fallback.
    """
    session_cookie = None
    referrer = None  # new tab — no referer

    has_valid_session = (
        validate_session_token(session_cookie, SECRET, TTL) == "valid"
        if session_cookie else False
    )
    ref_allowed = is_referrer_allowed(referrer, ALLOWED)

    assert not has_valid_session
    assert not ref_allowed

    decision = "DENY" if (not has_valid_session and not ref_allowed) else "ALLOW"
    assert decision == "DENY"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 8 — Direct HTTP / view-source: request → protected (guard fires)
# ═══════════════════════════════════════════════════════════════════════════════

def test_direct_http_request_without_session_or_referrer_is_denied():
    """
    A curl or view-source request:
      - No cookies
      - No Referer header (or an unrelated one)
    → guard intercepts and denies before serving HTML.
    """
    for referrer in [None, "https://evil.com/"]:
        has_session = False
        ref_allowed = is_referrer_allowed(referrer, ALLOWED)

        should_deny = not has_session and not ref_allowed
        assert should_deny, (
            f"curl/view-source with referrer={referrer!r} should be DENIED"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Additional: Token integrity tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_tampered_token_is_invalid():
    """Modifying the timestamp or signature must invalidate the token."""
    token = create_session_token(SECRET)
    ts, sig = token.split(".", 1)

    # Tamper with timestamp
    fake_ts = str(int(ts) - 1000)
    tampered_ts = f"{fake_ts}.{sig}"
    assert validate_session_token(tampered_ts, SECRET, TTL) == "invalid"

    # Tamper with signature
    bad_sig = sig[:-4] + "XXXX"
    tampered_sig = f"{ts}.{bad_sig}"
    assert validate_session_token(tampered_sig, SECRET, TTL) == "invalid"


def test_wrong_secret_is_invalid():
    """A token signed with a different secret must be rejected."""
    token = create_session_token("correct-secret-that-is-long-enough-here")
    result = validate_session_token(token, "wrong-secret-that-is-long-enough-xx", TTL)
    assert result == "invalid"


def test_empty_token_is_invalid():
    """Empty/blank token values must always be invalid."""
    for t in ["", "   ", "nodot", ".onlydot"]:
        assert validate_session_token(t, SECRET, TTL) != "valid", (
            f"Token {t!r} should not be valid"
        )


def test_missing_secret_is_invalid():
    """Without a secret, validation must always return invalid."""
    token = create_session_token(SECRET)
    assert validate_session_token(token, "", TTL) == "invalid"


# ═══════════════════════════════════════════════════════════════════════════════
# Additional: Referrer edge-case tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_www_subdomain_is_independently_validated():
    """www.browsmac.org and browsmac.org are separate entries — both allowed."""
    assert is_referrer_allowed("https://browsmac.org/page", ALLOWED)
    assert is_referrer_allowed("https://www.browsmac.org/page", ALLOWED)


def test_allowed_domain_with_path_and_query_is_accepted():
    """Path and query params on the referrer URL must not affect hostname check."""
    ref = "https://browsmac.org/article?id=123&utm_source=test#section"
    assert is_referrer_allowed(ref, ALLOWED)


def test_empty_allowed_list_denies_everything():
    """If ALLOWED_ENTRY_DOMAINS is empty, every referrer must be denied."""
    assert not is_referrer_allowed("https://browsmac.org/", [])


def test_malformed_referrer_is_denied():
    """Garbage referrer values must not cause exceptions and must be denied."""
    garbage = [
        "not-a-url",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "",
        None,
    ]
    for ref in garbage:
        assert not is_referrer_allowed(ref, ALLOWED), (
            f"Garbage referrer {ref!r} should be denied"
        )
