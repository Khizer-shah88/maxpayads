"""
Domain Glossary — the canonical vocabulary of the PPC network.

Every term below is the exact word used in code, comments, API payloads and
stored documents. Older spellings are still read from the database and still
accepted on API input, but they are rewritten to the canonical term before
anything else sees them. Nothing outside this module should spell a legacy
term out.

Redirect chain vocabulary
    Anchor      first redirect domain that receives the Smartlink   (was "link")
    Inter       intermediate redirect domain after the Anchor       (was "intermediate")
    Prelander   optional page shown before the final Offer          (was "last")

Operating systems
    Windows, Android/APK, Mac, iOS — a fixed enum. No new OS values.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.constants import (
    DOMAIN_TYPE_ANCHOR,
    DOMAIN_TYPE_INTER,
    DOMAIN_TYPE_LEGACY_MAP,
    DOMAIN_TYPE_PRELANDER,
    DOMAIN_TYPE_REVERSE_LEGACY_MAP,
    OS_ANDROID,
    OS_IOS,
    OS_MAC,
    OS_WINDOWS,
    VALID_DOMAIN_TYPES,
    VALID_OS_TYPES,
)

# Display order for the three domain types: the order traffic travels through them.
DOMAIN_TYPE_ORDER = (DOMAIN_TYPE_ANCHOR, DOMAIN_TYPE_INTER, DOMAIN_TYPE_PRELANDER)

# Human-readable labels, for API descriptions and admin UI.
DOMAIN_TYPE_LABELS: Dict[str, str] = {
    DOMAIN_TYPE_ANCHOR: "Anchor",
    DOMAIN_TYPE_INTER: "Inter",
    DOMAIN_TYPE_PRELANDER: "Prelander",
}


# ── Domain types ──────────────────────────────────────────────────────────────

def normalize_domain_type(value: Any, default: Optional[str] = None) -> Optional[str]:
    """
    Return the canonical domain type for `value`.

    Accepts the canonical terms (anchor/inter/prelander) and the legacy ones
    (link/intermediate/last). Anything else returns `default`.
    """
    key = (value or "").strip().lower() if isinstance(value, str) else ""
    if not key:
        return default
    key = DOMAIN_TYPE_LEGACY_MAP.get(key, key)
    return key if key in VALID_DOMAIN_TYPES else default


def legacy_domain_type(value: Any) -> Optional[str]:
    """Return the legacy spelling of a domain type — only for writing legacy data."""
    canonical = normalize_domain_type(value)
    return DOMAIN_TYPE_REVERSE_LEGACY_MAP.get(canonical) if canonical else None


def domain_type_filter(value: Any) -> Optional[dict]:
    """
    Build a Mongo filter fragment matching a domain type in either spelling.

        {"domain_type": domain_type_filter("prelander")}
        -> {"domain_type": {"$in": ["prelander", "last"]}}

    Documents written before migration 005 still carry the legacy value, so
    every read goes through this. Writes always store the canonical term.
    """
    canonical = normalize_domain_type(value)
    if not canonical:
        return None
    spellings = [canonical]
    legacy = DOMAIN_TYPE_REVERSE_LEGACY_MAP.get(canonical)
    if legacy:
        spellings.append(legacy)
    return {"$in": spellings}


# ── Operating systems ─────────────────────────────────────────────────────────

# How raw OS names (from user-agent parsing, API input, stored data) map onto
# the fixed OS enum.
#
# NOTE ON iOS: routing currently resolves iOS traffic into the Mac bucket, so
# `ios` normalizes to `mac` here. That keeps iOS a recognised glossary term on
# input while guaranteeing an iOS-targeted rule still matches real traffic —
# rather than validating cleanly and then never matching anything. This single
# entry is the only place that decision lives; when the OS routing rule is
# specified, changing `OS_IOS: OS_MAC` to `OS_IOS: OS_IOS` makes iOS standalone
# everywhere at once.
_OS_ALIASES: Dict[str, str] = {
    OS_WINDOWS: OS_WINDOWS,
    "win": OS_WINDOWS,
    "win32": OS_WINDOWS,
    "windows phone": OS_WINDOWS,
    "linux": OS_WINDOWS,
    "ubuntu": OS_WINDOWS,
    OS_MAC: OS_MAC,
    "mac os": OS_MAC,
    "mac os x": OS_MAC,
    "os x": OS_MAC,
    "macos": OS_MAC,
    "osx": OS_MAC,
    "darwin": OS_MAC,
    OS_IOS: OS_MAC,
    "iphone": OS_MAC,
    "ipad": OS_MAC,
    "ipados": OS_MAC,
    OS_ANDROID: OS_ANDROID,
    "apk": OS_ANDROID,
    "android/apk": OS_ANDROID,
}


def normalize_os(value: Any, default: Optional[str] = None) -> Optional[str]:
    """
    Return the OS enum value for a raw OS name, or `default` if unrecognised.

    This is the single OS normalizer for the whole system — targeting, campaign
    selection and prelander selection all resolve OS through it so they can
    never disagree about what a visitor is running.

    Versioned user-agent spellings also resolve: "Mac OS X 10.15" and
    "Windows NT 10.0" match via the longest known alias prefix, so a raw UA
    OS string normalizes the same way as the bare family name.
    """
    key = (value or "").strip().lower() if isinstance(value, str) else ""
    if not key:
        return default
    mapped = _OS_ALIASES.get(key)
    if mapped:
        return mapped
    # Longest-alias-first prefix match: "mac os x 10.15" → "mac os x" → mac.
    # Checking longest first keeps "mac os x …" from stopping at "mac os".
    for alias in sorted(_OS_ALIASES, key=len, reverse=True):
        if alias and key.startswith(alias + " "):
            return _OS_ALIASES[alias]
    return key if key in VALID_OS_TYPES else default
