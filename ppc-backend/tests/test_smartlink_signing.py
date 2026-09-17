"""
Smartlink signing — tests.

Covers the signing service (generation, binding, tamper rejection) and the
/click validation behavior (valid token passes, tampered token 403s, legacy
links unaffected unless strict mode is on).
"""
import pytest

from app.services import smartlink_signing as sls

PUB = "PUB_LUKLLIZW"
SITE = "SITE_2PRBE5E1"


# ── generation ────────────────────────────────────────────────────────────────

def test_token_is_generated_and_deterministic():
    """Same pub/site/nonce → same token; the system generates it, not the client."""
    t1 = sls.generate_link_token(PUB, SITE, "nonce1")
    t2 = sls.generate_link_token(PUB, SITE, "nonce1")
    assert t1 and t1 == t2
    assert len(t1) == 32  # 128-bit truncated HMAC — high entropy, url-safe


def test_every_generated_link_has_a_unique_nonce_and_token():
    """Per-link nonce: two generated links differ, yet each validates."""
    p1 = sls.signed_link_params(PUB, SITE)
    p2 = sls.signed_link_params(PUB, SITE)
    # Nonces differ → tokens differ → links are not byte-identical
    assert p1["n"] != p2["n"]
    assert p1["hmac"] != p2["hmac"]
    # But each token verifies against its own nonce
    assert sls.verify_link_token(PUB, SITE, p1["hmac"], p1["n"])
    assert sls.verify_link_token(PUB, SITE, p2["hmac"], p2["n"])


def test_token_is_bound_to_tag_ids():
    """A token for one link cannot be reused on different Tag IDs."""
    token = sls.generate_link_token(PUB, SITE)
    assert sls.verify_link_token(PUB, SITE, token)
    # Swapped/moved to another publisher or website → invalid
    assert not sls.verify_link_token("PUB_OTHERXXX", SITE, token)
    assert not sls.verify_link_token(PUB, "SITE_OTHER9", token)
    # site omitted (manual publisher) is a DIFFERENT message
    assert not sls.verify_link_token(PUB, None, token)


# ── tamper prevention ─────────────────────────────────────────────────────────

def test_modified_hash_character_is_rejected():
    token = sls.generate_link_token(PUB, SITE, "n1")
    for pos in (0, 7, 15, 31):
        flipped = list(token)
        flipped[pos] = "0" if flipped[pos] != "0" else "1"
        assert not sls.verify_link_token(PUB, SITE, "".join(flipped), "n1")


def test_arbitrary_random_token_is_rejected():
    assert not sls.verify_link_token(PUB, SITE, "deadbeefdeadbeefdeadbeefdeadbeef")
    assert not sls.verify_link_token(PUB, SITE, "")
    assert not sls.verify_link_token(PUB, SITE, "x" * 32)
    assert not sls.verify_link_token(PUB, SITE, "a" * 64)  # right length, wrong MAC


def test_modified_params_with_valid_old_token_rejected():
    """Change ANY character of the tag values while keeping the old hash → reject."""
    token = sls.generate_link_token(PUB, SITE, "n1")
    tampered_pub = PUB[:-1] + ("X" if PUB[-1] != "X" else "Y")
    assert not sls.verify_link_token(tampered_pub, SITE, token, "n1")


# ── /click endpoint validation ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_click_with_valid_signature_passes_to_pipeline(async_client, db, test_publisher, test_website):
    """A properly signed link reaches the pipeline (redirect, not 403)."""
    nonce = sls.new_link_nonce()
    token = sls.generate_link_token(str(test_publisher["_id"]), None, nonce)
    resp = await async_client.get(
        f"/click?pub={test_publisher['_id']}&hmac={token}&n={nonce}",
        follow_redirects=False,
    )
    # Pipeline ran (redirect/fallback) — NOT the 403 invalid-link screen
    assert resp.status_code in (200, 302), f"expected pipeline response, got {resp.status_code}: {resp.text[:120]}"


@pytest.mark.asyncio
async def test_click_with_tampered_signature_is_403(async_client, test_publisher):
    """Modifying any character of the hash → 403 invalid-link screen."""
    token = sls.generate_link_token(str(test_publisher["_id"]), None, "n1")
    tampered = ("0" if token[0] != "0" else "1") + token[1:]
    resp = await async_client.get(
        f"/click?pub={test_publisher['_id']}&hmac={tampered}&n=n1",
        follow_redirects=False,
    )
    assert resp.status_code == 403
    body = resp.text
    assert "Invalid or expired link" in body
    # The screen leaks nothing
    for leak in ("PUB_", str(test_publisher["_id"]), "hmac", "Traceback"):
        assert leak not in body


@pytest.mark.asyncio
async def test_click_with_arbitrary_token_is_403(async_client, test_publisher):
    resp = await async_client.get(
        f"/click?pub={test_publisher['_id']}&hmac={'f' * 32}", follow_redirects=False,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_click_without_token_still_works_legacy(async_client, test_publisher, monkeypatch):
    """Default (non-strict) mode: legacy token-less links keep working."""
    import app.config as config
    monkeypatch.setattr(config.get_settings(), "SMARTLINK_HASH_REQUIRED", False, raising=False)
    resp = await async_client.get(
        f"/click?pub={test_publisher['_id']}", follow_redirects=False,
    )
    assert resp.status_code in (200, 302)


@pytest.mark.asyncio
async def test_strict_mode_rejects_missing_token(async_client, test_publisher, monkeypatch):
    import app.config as config
    monkeypatch.setattr(config.get_settings(), "SMARTLINK_HASH_REQUIRED", True, raising=False)
    resp = await async_client.get(
        f"/click?pub={test_publisher['_id']}", follow_redirects=False,
    )
    assert resp.status_code == 403
    # …and a valid signed link still passes in strict mode
    token = sls.generate_link_token(str(test_publisher["_id"]), None, "n")
    resp2 = await async_client.get(
        f"/click?pub={test_publisher['_id']}&hmac={token}&n=n", follow_redirects=False,
    )
    assert resp2.status_code in (200, 302)