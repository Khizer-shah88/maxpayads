"""
Domain Glossary — terminology tests.

These lock in the two properties the glossary migration depends on:
  1. Canonical terms are what the system produces.
  2. Legacy spellings are still understood, so data written before
     migration 005 (and API clients that predate it) keep working.

Pure unit tests — no database required.
"""
import pytest

from app.core.constants import (
    DOMAIN_TYPE_ANCHOR,
    DOMAIN_TYPE_INTER,
    DOMAIN_TYPE_PRELANDER,
    OS_ANDROID,
    OS_MAC,
    OS_WINDOWS,
    VALID_DOMAIN_TYPES,
    VALID_OS_TYPES,
)
from app.core.glossary import (
    domain_type_filter,
    legacy_domain_type,
    normalize_domain_type,
    normalize_os,
)


# ── the vocabulary itself ─────────────────────────────────────────────────────

def test_domain_types_are_the_glossary_terms():
    assert VALID_DOMAIN_TYPES == {"anchor", "inter", "prelander"}


def test_os_enum_is_the_glossary_enum():
    assert VALID_OS_TYPES == {"windows", "android", "mac", "ios"}


# ── domain types ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("legacy,canonical", [
    ("link", DOMAIN_TYPE_ANCHOR),
    ("intermediate", DOMAIN_TYPE_INTER),
    ("last", DOMAIN_TYPE_PRELANDER),
])
def test_legacy_domain_types_normalize_to_glossary_terms(legacy, canonical):
    assert normalize_domain_type(legacy) == canonical
    assert normalize_domain_type(legacy.upper()) == canonical
    assert normalize_domain_type(f"  {legacy} ") == canonical


@pytest.mark.parametrize("canonical", ["anchor", "inter", "prelander"])
def test_canonical_domain_types_pass_through(canonical):
    assert normalize_domain_type(canonical) == canonical
    assert legacy_domain_type(canonical) in ("link", "intermediate", "last")


def test_unknown_domain_type_yields_default():
    assert normalize_domain_type("sideways") is None
    assert normalize_domain_type("", default=DOMAIN_TYPE_ANCHOR) == DOMAIN_TYPE_ANCHOR
    assert normalize_domain_type(None, default=DOMAIN_TYPE_ANCHOR) == DOMAIN_TYPE_ANCHOR


def test_domain_type_filter_matches_both_spellings():
    """Every read must still see documents written before migration 005."""
    assert domain_type_filter("prelander") == {"$in": ["prelander", "last"]}
    assert domain_type_filter("last") == {"$in": ["prelander", "last"]}
    assert domain_type_filter("anchor") == {"$in": ["anchor", "link"]}
    assert domain_type_filter("inter") == {"$in": ["inter", "intermediate"]}
    assert domain_type_filter("sideways") is None


# ── OS enum ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("Windows", OS_WINDOWS),
    ("windows", OS_WINDOWS),
    ("linux", OS_WINDOWS),
    ("Mac OS X", OS_MAC),
    ("macos", OS_MAC),
    ("Android", OS_ANDROID),
    ("apk", OS_ANDROID),
])
def test_os_names_resolve_onto_the_enum(raw, expected):
    assert normalize_os(raw) == expected


def test_ios_resolves_into_the_mac_bucket():
    """
    iOS is a glossary term and is accepted everywhere, but routing currently
    resolves iOS traffic into the Mac bucket. Normalizing it the same way keeps
    an iOS-targeted rule matching real traffic instead of matching nothing.
    Change `_OS_ALIASES[OS_IOS]` when the OS routing rule makes iOS standalone.
    """
    assert normalize_os("ios") == OS_MAC
    assert normalize_os("iPhone") == OS_MAC


def test_unknown_os_yields_default():
    assert normalize_os("plan9") is None
    assert normalize_os("", default=OS_WINDOWS) == OS_WINDOWS
    assert normalize_os(None) is None


# ── schemas speak the glossary ────────────────────────────────────────────────

def test_domain_schema_accepts_legacy_type_and_stores_canonical():
    from app.schemas.redirection_domain_schema import RedirectionDomainCreate

    assert RedirectionDomainCreate(domain="a.com", domain_type="last").domain_type == "prelander"
    assert RedirectionDomainCreate(domain="a.com", domain_type="prelander").domain_type == "prelander"


def test_domain_schema_rejects_unknown_type():
    from pydantic import ValidationError
    from app.schemas.redirection_domain_schema import RedirectionDomainCreate

    with pytest.raises(ValidationError):
        RedirectionDomainCreate(domain="a.com", domain_type="sideways")


def test_offer_accepts_legacy_payout_as_cpc():
    from app.schemas.offer_schema import OfferCreate, OfferUpdate

    assert OfferCreate(name="o", offer_url="https://e.com", payout=0.25).cpc == 0.25
    assert OfferCreate(name="o", offer_url="https://e.com", cpc=0.25).cpc == 0.25

    update = OfferUpdate(payout=1.5).model_dump(exclude_unset=True)
    assert update == {"cpc": 1.5}


def test_offer_os_types_resolve_onto_the_enum():
    from app.schemas.offer_schema import OfferCreate

    offer = OfferCreate(
        name="o",
        offer_url="https://e.com",
        os_types=["iOS", "WINDOWS", "plan9", "windows"],
    )
    assert offer.os_types == [OS_MAC, OS_WINDOWS]


def test_chain_accepts_legacy_field_names():
    from app.models.redirect_chain import (
        CreateRedirectChainRequest,
        chain_inter_domain,
        chain_prelander_pool,
    )

    legacy = CreateRedirectChainRequest(
        name="chain",
        anchor_domain="a.com",
        intermediate_domain="i.com",
        pre_lander_pool=["p.com"],
    )
    canonical = CreateRedirectChainRequest(
        name="chain",
        anchor_domain="a.com",
        inter_domain="i.com",
        prelander_pool=["p.com"],
    )
    assert legacy.inter_domain == canonical.inter_domain == "i.com"
    assert legacy.prelander_pool == canonical.prelander_pool == ["p.com"]


def test_stored_chains_read_through_either_key():
    """Chains written before migration 005 still resolve."""
    from app.models.redirect_chain import chain_inter_domain, chain_prelander_pool

    assert chain_inter_domain({"intermediate_domain": "old.com"}) == "old.com"
    assert chain_inter_domain({"inter_domain": "new.com"}) == "new.com"
    assert chain_prelander_pool({"pre_lander_pool": ["a.com"]}) == ["a.com"]
    assert chain_prelander_pool({"prelander_pool": ["b.com"]}) == ["b.com"]
    assert chain_prelander_pool({}) == []
    assert chain_inter_domain({}) is None
