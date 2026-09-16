"""
Prelander API — returns file details, offer URL, and password.

Endpoint: GET /prelander/resolve/{slug}
  - Decodes the XOR-encrypted slug from traffic_router.py
  - If the request host is an Inter domain → 302 to the Prelander domain /d/{slug}
    (completing the three-step flow: Anchor → Inter → Prelander)
  - Otherwise → returns prelander data (offer_url, password, os, etc.)

Three-step flow (bypass OFF, both Inter + Prelander configured):
  1. /click  →  inter_domain/d/{slug}              (entry point)
  2. inter/d/{slug} loads, calls /api/prelander/resolve/{slug}
     → backend detects Inter host → 302 to prelander_domain/d/{slug}
  3. prelander/d/{slug} loads, calls /api/prelander/resolve/{slug}
     → backend returns prelander data → page renders template

Two-step flow (bypass OFF, only Prelander OR only Inter configured):
  1. /click  →  prelander_domain/d/{slug}
  2. prelander/d/{slug} calls /api/prelander/resolve/{slug} → data returned

Bypass ON (direct_redirect_mode):
  1. /click  →  campaign URL directly (no prelander at all)
"""
import logging
from fastapi import APIRouter, Query, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from typing import Optional
from bson import ObjectId
import base64
from app.core.constants import DOMAIN_TYPE_INTER, DOMAIN_TYPE_PRELANDER
from app.core.glossary import domain_type_filter, normalize_domain_type
from app.dependencies import get_db

logger = logging.getLogger(__name__)

_XOR_KEY = "mxp2026"


def get_redis_safe():
    """Redis client for the authorization gate; None when not yet connected."""
    try:
        from app.cache.redis_client import get_redis
        return get_redis()
    except Exception:
        return None


def _decode_slug(slug: str) -> Optional[dict]:
    """
    Decode an XOR-encrypted slug → {os, timestamp, offer_id, campaign_id, country_code}.
    Returns None if invalid or if the timestamp is older than 1 hour (expired).
    """
    try:
        padded = slug + "=" * (4 - len(slug) % 4) if len(slug) % 4 else slug
        xored = base64.urlsafe_b64decode(padded)
        raw = "".join(chr(b ^ ord(_XOR_KEY[i % len(_XOR_KEY)])) for i, b in enumerate(xored))
        if ":" not in raw:
            return None
        parts = raw.split(":")
        result = {"os": parts[0]}

        # parts[1] is the timestamp — validate expiry (3600s = 1 hour)
        if len(parts) >= 2 and parts[1]:
            try:
                import time
                slug_ts = int(parts[1])
                age = time.time() - slug_ts
                if age > 3600:  # 1 hour expiry
                    logger.warning("[PRELANDER] Slug expired (age=%ds)", int(age))
                    return None
                if age < -60:   # Clock skew guard — reject future timestamps
                    logger.warning("[PRELANDER] Slug from the future, rejected")
                    return None
            except (ValueError, TypeError):
                return None

        if len(parts) >= 3 and parts[2]:
            result["offer_id"] = parts[2]
        if len(parts) >= 4 and parts[3]:
            result["campaign_id"] = parts[3]
        if len(parts) >= 5 and parts[4]:
            result["country_code"] = parts[4]
        return result
    except Exception:
        return None


router = APIRouter(prefix="/prelander", tags=["Prelander"])


async def _resolve_bypass_destination(
    db,
    campaign_id: Optional[str],
    offer_id: Optional[str],
) -> Optional[str]:
    """
    Resolve the bypass destination for a slug: the Offer's URL when the offer
    itself has direct_redirect_mode, else the Campaign URL when the campaign
    has it. Mirrors the priority in traffic_router.route_click (offer overrides
    campaign). Returns None when bypass is OFF anywhere — the caller then
    continues the normal prelander hop.
    """
    if offer_id:
        try:
            offer = await db.offers.find_one({"_id": ObjectId(offer_id)})
            if offer and offer.get("direct_redirect_mode"):
                return (
                    offer.get("offer_url")
                    or offer.get("default_offer_url")
                    or offer.get("url")
                )
        except Exception:
            pass

    if campaign_id:
        try:
            camp_oid = ObjectId(campaign_id)
        except Exception:
            return None
        camp = await db.campaigns.find_one({"_id": camp_oid})
        if camp and camp.get("direct_redirect_mode"):
            return (
                camp.get("default_offer_url")
                or camp.get("offer_url")
                or camp.get("url")
            )
    return None


async def _request_is_authorized(
    request: Request,
    slug: str,
    db,
) -> bool:
    """
    Server-side prelander authorization decision (DOMAIN != AUTHORIZATION).

    Valid when the visitor carries an authorization session created at
    Smartlink click time (stage_authorize_prelander) that matches this exact
    browser (client IP + User-Agent fingerprint) and this exact slug.

    A PRELANDER_AUTH_REQUIRED=False setting (env) disables the gate — a safety
    valve so a misconfiguration can never lock the whole prelander flow.
    Default: enabled.
    """
    import os
    from app.utils.ip_utils import get_client_ip
    from app.services import prelander_auth_service as pas

    # Kill switch — off only when explicitly disabled in the environment.
    if os.getenv("PRELANDER_AUTH_REQUIRED", "true").strip().lower() in ("false", "0", "no", "off"):
        return True

    try:
        redis = get_redis_safe()
        if redis is None:
            # Redis unavailable at validation time — fail CLOSED for protected
            # content (the neutral page), never open. Log loudly so ops sees it.
            logger.error("[PRELANDER-AUTH] Redis unavailable at validation — denying")
            return False

        headers = dict(request.headers)
        ip = get_client_ip(headers, request.client.host if request.client else "0.0.0.0")
        user_agent = headers.get("user-agent", "")
        cookie_reference = request.cookies.get(pas.COOKIE_NAME)

        authorized = await pas.validate_authorization(
            slug=slug,
            ip=ip,
            user_agent=user_agent,
            redis=redis,
            cookie_reference=cookie_reference,
        )
        if not authorized:
            logger.info(
                "[PRELANDER-AUTH] Denied prelander access for slug=%s… ip=%s",
                slug[:10], ip,
            )
        return authorized
    except Exception as e:
        # Validation itself failed — deny, but never leak why to the client.
        logger.error("[PRELANDER-AUTH] Validation error (denying): %s", e)
        return False


async def _host_in_chain_sequence(db, host: str) -> bool:
    """
    True when `host` is positioned inside an active chain's managed sequence
    (its Inter domain or any extra hop) — meaning the chain still has a hop
    after it (or a Prelander pool to draw from).
    """
    from app.services.domain_service import normalize_domain
    from app.models.redirect_chain import chain_inter_domain

    host = normalize_domain(host)
    if not host:
        return False

    chains = await db.redirect_chains.find({"status": "active"}).to_list(length=200)
    for chain in chains:
        sequence: list = []
        inter = chain_inter_domain(chain)
        if inter:
            sequence.append(inter)
        sequence.extend([d for d in (chain.get("extra_domains") or []) if d])
        if host in [normalize_domain(d) for d in sequence if d]:
            return True
    return False


async def _resolve_next_hop(db, current_host: str) -> Optional[str]:
    """
    Next managed hop for a visitor currently on `current_host` (Bypass OFF).

    Chain override first: when the current host is positioned inside an active
    chain's sequence (its Inter domain or an extra hop), the next hop is the
    entry AFTER the current host — the next extra domain, or a weighted pick
    from the chain's Prelander pool after the last hop.

    No chain position (host not part of any chain) → classic redirection-domain
    flow: the publisher-assigned (or global) Active Prelander domain.

    Every hop is forced to an absolute https:// URL — a bare hostname stored
    in a chain field would produce a RELATIVE /d/{slug} destination and the
    browser would resolve it against the current page's domain.

    Returns a URL (https://host) or None when there is nothing to hop to —
    the caller then serves prelander data on the current host.
    """
    from app.services.domain_service import (
        domain_to_url, normalize_domain, resolve_domain_url, select_active_prelander,
    )
    from app.models.redirect_chain import chain_inter_domain, chain_prelander_pool

    host = normalize_domain(current_host)
    if not host:
        return None

    # ── Chain override: host is inside a chain sequence ───────────────────────
    chains = await db.redirect_chains.find({"status": "active"}).to_list(length=200)
    for chain in chains:
        sequence: list = []
        inter = chain_inter_domain(chain)
        if inter:
            sequence.append(inter)
        sequence.extend([d for d in (chain.get("extra_domains") or []) if d])

        normalized_seq = [normalize_domain(d) for d in sequence if d]
        if host not in normalized_seq:
            continue

        idx = normalized_seq.index(host)
        # Next extra hop after the current position
        if idx + 1 < len(normalized_seq):
            next_url = domain_to_url(normalized_seq[idx + 1])
            # Never hop to ourselves — that would loop the visitor forever.
            if next_url and normalize_domain(next_url) != host:
                return next_url
        # Current host is the last hop → weighted pick from the Prelander pool
        pool = [normalize_domain(d) for d in chain_prelander_pool(chain) if d]
        if pool:
            pick = await select_active_prelander(db, pool)
            if pick and normalize_domain(pick) != host:
                return domain_to_url(pick)
            # No ACTIVE prelander in the pool (or the pick IS this host) →
            # caller serves data here
            return None

    # ── Classic flow: host is not part of any chain sequence ──────────────────
    publisher_ids_doc = await db.redirection_domains.find_one({"domain": host, "status": "active"})
    publisher_ids = (publisher_ids_doc or {}).get("publisher_ids") or []
    publisher_id = publisher_ids[0] if publisher_ids else None
    prelander_base = await resolve_domain_url(db, DOMAIN_TYPE_PRELANDER, publisher_id)

    # Normalize: resolve_domain_url may return a bare hostname from legacy
    # system_settings — force it through domain_to_url so the /d page always
    # navigates to an absolute https:// URL.
    if prelander_base:
        if not prelander_base.startswith(("http://", "https://")):
            prelander_base = domain_to_url(prelander_base)
        if prelander_base and normalize_domain(prelander_base) != host:
            return prelander_base.rstrip("/")
    return None


@router.get("/domain-type")
async def get_domain_type(
    host: str,
    slug: Optional[str] = Query(None, description="Prelander slug — enables bypass detection"),
    db=Depends(get_db),
):
    """
    Returns the configured domain_type for a hostname, plus the next hop for a
    visitor currently on that host. Called by the /d/[slug] page on load to
    decide where to go next.

    Response: { "domain_type": "anchor" | "inter" | "prelander" | "unknown",
                "prelander_domain": "https://…" | null,      # next hop (legacy name)
                "last_domain": mirrored for pre-glossary bundles,
                "bypass_redirect_url": "https://campaign.com" | null }

    The next hop is chain-aware: a host positioned inside a chain's sequence
    (Inter or an extra hop) gets the NEXT hop — the following extra domain or
    the weighted Prelander pool pick after the last hop. Hosts not in any
    chain get the legacy publisher/global Prelander domain.

    When slug is supplied and the host is NOT the Prelander domain, the slug is
    decoded and the campaign/offer bypass checked: bypass ON returns the
    Campaign URL in bypass_redirect_url so the /d page (after its 0.75s dwell on
    the Inter domain) sends the visitor straight to the campaign.
    """
    from app.services.domain_service import normalize_domain

    h = normalize_domain(host)
    if not h:
        return {"domain_type": "unknown", "prelander_domain": None, "last_domain": None, "bypass_redirect_url": None}

    doc = await db.redirection_domains.find_one({"domain": h, "status": "active"})
    domain_type = normalize_domain_type(doc.get("domain_type"), default="unknown") if doc else "unknown"

    # Is this host positioned INSIDE a chain sequence (Inter or an extra hop)?
    # A mid-chain host keeps hopping even when it is also registered as a
    # Prelander domain — the admin's configured sequence wins over the type.
    in_chain_sequence = await _host_in_chain_sequence(db, h)

    # ── Bypass detection (spec: Inter dwells 0.75s, then Campaign URL) ────────
    # Applies to every host that is not the FINAL prelander: Inter, extra
    # chain hops, and prelander-typed domains positioned mid-chain.
    bypass_redirect_url = None
    if (domain_type != DOMAIN_TYPE_PRELANDER or in_chain_sequence) and slug:
        decoded = _decode_slug(slug)
        if decoded:
            target = await _resolve_bypass_destination(
                db, decoded.get("campaign_id"), decoded.get("offer_id")
            )
            if target:
                from app.services.traffic_router import _clean_campaign_url
                bypass_redirect_url = _clean_campaign_url(target)

    # ── Next hop (chain-aware) ───────────────────────────────────────────────
    prelander_domain = None
    if (domain_type != DOMAIN_TYPE_PRELANDER or in_chain_sequence) and not bypass_redirect_url:
        next_hop = await _resolve_next_hop(db, h)
        if next_hop and normalize_domain(next_hop) != h:
            prelander_domain = next_hop.rstrip("/")

    return {
        "domain_type": domain_type,
        "prelander_domain": prelander_domain,
        "last_domain": prelander_domain,
        "bypass_redirect_url": bypass_redirect_url,
    }


@router.get("/resolve/{slug}")
async def resolve_slug(slug: str, request: Request, db=Depends(get_db)):
    """
    Main prelander resolver. Called by the /d/[slug] Next.js page.

    When the requesting host is an Inter domain:
      → 302 redirect to {prelander_domain}/d/{slug}  (completes the Inter hop)

    When the requesting host is a Prelander domain or any other host:
      → Returns prelander data JSON (offer_url, password, os, etc.)
    """
    from app.services.domain_service import normalize_domain

    # Use X-Prelander-Host (sent by browser JS) OR Host header (sent by nginx).
    # X-Prelander-Host is the real browser domain even through the Next.js proxy.
    # Host header is set by nginx to $host so it's also reliable when nginx
    # routes /api/prelander directly to FastAPI (as in the catch-all block).
    xph = request.headers.get("x-prelander-host", "").strip()
    host_header = request.headers.get("host", "").strip()

    # Prefer X-Prelander-Host; fall back to Host; normalize both
    prelander_host = normalize_domain(xph or host_header)
    
    # Also check the raw host without port stripping (normalize_domain already strips port)
    if not prelander_host:
        prelander_host = normalize_domain(host_header)

    # ── Domain-type detection & hop ───────────────────────────────────────────
    # The visitor is somewhere in the redirect chain sequence:
    #   Anchor → Inter → [extra hops] → Prelander Pool (Bypass OFF)
    # Decide whether this host serves the prelander data or forwards to the
    # next hop:
    #   - A Prelander-typed domain serves the data, UNLESS the admin positioned
    #     it mid-chain (as an extra hop) — the configured sequence wins.
    #   - Any other host (Inter, extra hop, unknown) hops to the next managed
    #     domain: the next chain hop, the weighted Prelander pool pick after
    #     the last hop, or the legacy publisher/global Prelander domain.
    if prelander_host:
        prelander_doc = await db.redirection_domains.find_one({
            "domain": prelander_host,
            "domain_type": domain_type_filter(DOMAIN_TYPE_PRELANDER),
            "status": "active",
        })
        in_chain_sequence = await _host_in_chain_sequence(db, prelander_host)
        should_hop = (prelander_doc is None) or in_chain_sequence

        if should_hop:
            # Bypass check first (spec): Bypass ON → straight to the Campaign
            # URL from the Inter/chain domain, never touching the Prelander.
            # Bypass ON: Anchor → Inter (logs, 0.75s dwell) → Campaign URL —
            # decode the slug and check the campaign/offer direct_redirect_mode.
            # ON → 302 straight to the Campaign URL, never the Prelander domain.
            # Same server-side authorization gate as the prelander data: the
            # bypass destination is a protected campaign URL.
            decoded_bypass = _decode_slug(slug)
            if decoded_bypass:
                if not await _request_is_authorized(request, slug, db):
                    return JSONResponse(status_code=404, content={"detail": "Not found"})
                bypass_url = await _resolve_bypass_destination(
                    db, decoded_bypass.get("campaign_id"), decoded_bypass.get("offer_id")
                )
                if bypass_url:
                    from app.services.traffic_router import _clean_campaign_url
                    clean = _clean_campaign_url(bypass_url)
                    logger.info(
                        "[PRELANDER] Bypass ON on host %s → direct campaign %s",
                        prelander_host, clean,
                    )
                    return RedirectResponse(
                        url=clean,
                        status_code=302,
                        headers={"Referrer-Policy": "no-referrer"},
                    )

            # Bypass OFF → chain-aware next hop (extra hops, then prelander pool)
            next_hop = await _resolve_next_hop(db, prelander_host)
            if next_hop:
                dest = f"{next_hop.rstrip('/')}/d/{slug}"
                logger.info("[PRELANDER] Hopping %s → %s", prelander_host, dest)
                return RedirectResponse(
                    url=dest,
                    status_code=302,
                    headers={"Referrer-Policy": "no-referrer"},
                )
        # Either on the Prelander domain already, or none configured → serve data

    # ── SERVER-SIDE AUTHORIZATION GATE ────────────────────────────────────────
    # DOMAIN != AUTHORIZATION: knowing the prelander URL is not sufficient.
    # Before any protected prelander data (offer URL, password, template HTML)
    # is built, the visitor must hold an authorization session created at
    # Smartlink click time (redirect_pipeline.stage_authorize_prelander) and
    # bound to this exact browser fingerprint and slug. Direct visits, shared
    # links, scrapers and replayed slugs without a session get the same neutral
    # 404 the page shows for invalid slugs — revealing nothing about the
    # prelander's existence or contents.
    if not await _request_is_authorized(request, slug, db):
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    # ── Normal resolve ─────────────────────────────────────────────────────────
    decoded = _decode_slug(slug)
    if not decoded:
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    return await _get_prelander_data(
        request, decoded["os"], db,
        offer_id=decoded.get("offer_id"),
        campaign_id=decoded.get("campaign_id"),
        country_code=decoded.get("country_code"),
    )


@router.get("/data")
async def get_prelander_data_legacy(
    request: Request,
    os: str = Query("windows", description="OS type: windows or mac"),
    pub: Optional[str] = Query(None, description="Publisher ID"),
    db=Depends(get_db),
):
    """
    Legacy endpoint — returns prelander data without a slug.

    Gated by the same server-side authorization as the slug route: without a
    slug there is no route binding, so only the cookie/fingerprint path can
    validate. An empty slug never matches any session, so unauthenticated
    direct calls get the neutral 404 — exactly like the frontend's invalid-
    slug page, revealing nothing.
    """
    if not await _request_is_authorized(request, "", db):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    return await _get_prelander_data(request, os, db)


async def _get_prelander_data(
    request: Request,
    os: str,
    db,
    offer_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    country_code: Optional[str] = None,
):
    """Core prelander data resolution logic."""
    os_lower = os.lower()

    # Prelander template override — if the host IS a Prelander domain, use its
    # template setting to pin the page to a specific OS. The browser's real
    # domain arrives as X-Prelander-Host (sent by the /d/[slug] page); the Host
    # header is only reliable when nginx routes /api/prelander straight to
    # FastAPI, so it stays as the fallback — same preference as resolve_slug.
    host = (
        request.headers.get("x-prelander-host", "").strip()
        or request.headers.get("host", "").split(":")[0].lower()
    )
    template_doc = None
    is_prelander_host = False
    if host:
        from app.services.domain_service import normalize_domain
        from app.services.prelander_service import get_template_for_domain
        normalized_host = normalize_domain(host)
        prelander_domain_doc = await db.redirection_domains.find_one({
            "domain_type": domain_type_filter(DOMAIN_TYPE_PRELANDER),
            "domain": normalized_host,
            "status": "active",
        })
        if prelander_domain_doc:
            is_prelander_host = True
            tpl = prelander_domain_doc.get("template", "default")
            if tpl == "mac":
                os_lower = "mac"
            elif tpl == "windows":
                os_lower = "windows"

            # Scenario rule: the selected prelander uses its assigned active
            # template, falling back to the OS Default Template when the
            # assigned one is unavailable. get_template_for_domain encodes both
            # steps; None means no active template exists at all → the visitor
            # skips the prelander (flagged in the response below).
            try:
                template_doc = await get_template_for_domain(db, normalized_host)
            except Exception as e:
                logger.warning(
                    "[PRELANDER] Template lookup failed for %s: %s", normalized_host, e
                )

    # Per-OS file metadata
    if os_lower == "mac":
        file_name, file_ext, file_size = "Setup", ".dmg", "4.2 MB"
        file_version, file_description = "1.0.0", "macOS Application Installer"
    else:
        file_name, file_ext, file_size = "Setup", ".exe", "3.8 MB"
        file_version, file_description = "1.0.0", "Windows Application Installer"

    offer_url = None
    password = None
    campaign_name = None

    # 1. Specific offer from slug — highest priority because TargetingEngine
    # resolved this specific offer as the winning destination.
    if offer_id:
        logger.info(f"[PRELANDER] Looking up offer_id from slug: {offer_id}")
        try:
            offer = await db.offers.find_one({"_id": ObjectId(offer_id), "status": "active"})
            if not offer:
                offer = await db.offers.find_one({"_id": offer_id, "status": "active"})
            if offer:
                logger.info(f"[PRELANDER] Found offer: {offer.get('name')} (ID: {offer_id})")
                offer_url = offer.get("offer_url")
                password = offer.get("password") or None
                if offer.get("campaign_id"):
                    try:
                        camp = await db.campaigns.find_one({"_id": ObjectId(offer["campaign_id"])})
                        if camp:
                            campaign_name = camp.get("name")
                            logger.info(f"[PRELANDER] Offer belongs to campaign: {campaign_name}")
                            if password is None and "password" not in offer:
                                password = camp.get("password")
                    except Exception:
                        pass
            else:
                logger.warning(f"[PRELANDER] Offer not found for ID: {offer_id}")
        except Exception as e:
            logger.warning(f"[PRELANDER] Error looking up offer: {e}")

    # 2. GEO rule — country-specific URL if no specific offer was matched
    if not offer_url and campaign_id and country_code:
        geo_rule = await db.geo_rules.find_one(
            {"campaign_id": campaign_id, "country_code": country_code.upper()},
            sort=[("priority", -1)],
        )
        if geo_rule and geo_rule.get("offer_url"):
            offer_url = geo_rule["offer_url"]
            password = geo_rule.get("password") or None

    # 3. Campaign from slug - extract URL when no specific offer/geo rule matched
    if campaign_id:
        logger.info(f"[PRELANDER] Looking up campaign_id from slug: {campaign_id}")
        try:
            camp = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
            if camp:
                if not campaign_name:
                    campaign_name = camp.get("name")
                    logger.info(f"[PRELANDER] Found campaign: {campaign_name} (ID: {campaign_id})")
                
                # Extract campaign URL when no more specific offer URL was found
                if not offer_url:
                    offer_url = (
                        camp.get("default_offer_url")
                        or camp.get("offer_url")
                        or camp.get("url")
                    )
                    if offer_url:
                        logger.info(f"[PRELANDER] Using campaign URL from slug: {offer_url}")
                    else:
                        logger.warning(f"[PRELANDER] Campaign {campaign_name} has no URL configured")
                
                if password is None:
                    password = camp.get("password")
            else:
                logger.warning(f"[PRELANDER] Campaign not found for ID: {campaign_id}")
        except Exception as e:
            logger.warning(f"[PRELANDER] Error looking up campaign: {e}")

    # 4. Fallback — match by domain, OS, or any active campaign
    if not offer_url:
        campaign = None
        req_host = request.headers.get("host", "").split(":")[0].lower()

        # Try to find campaign by landing page domain first
        if req_host:
            lp = await db.landing_pages.find_one({
                "status": "active",
                "lander_url": {"$regex": req_host, "$options": "i"},
            })
            if lp and lp.get("campaign_id"):
                try:
                    campaign = await db.campaigns.find_one({"_id": ObjectId(lp["campaign_id"]), "status": "active"})
                except Exception:
                    pass

        # Try to find campaign by device OS (case-insensitive)
        if not campaign:
            device_os = "windows" if os_lower == "windows" else "mac"
            campaign = await db.campaigns.find_one({
                "status": "active",
                "device_os": {"$regex": f"^{device_os}$", "$options": "i"},
            })
            logger.info(f"[PRELANDER] Campaign lookup by OS '{device_os}': {'found' if campaign else 'not found'}")

        # Try to find global campaign
        if not campaign:
            campaign = await db.campaigns.find_one({
                "status": "active",
                "device_os": {"$regex": "^global$", "$options": "i"},
            })
            logger.info(f"[PRELANDER] Campaign lookup by 'global': {'found' if campaign else 'not found'}")

        # Last resort: any active campaign
        if not campaign:
            campaign = await db.campaigns.find_one({"status": "active"})
            logger.info(f"[PRELANDER] Campaign lookup (any active): {'found' if campaign else 'not found'}")

        if campaign:
            campaign_name = campaign.get("name")
            logger.info(f"[PRELANDER] Resolved campaign: {campaign_name} (ID: {campaign.get('_id')})")
            
            # Try multiple field names for the campaign URL (different schemas used different names)
            offer_url = (
                campaign.get("default_offer_url")
                or campaign.get("offer_url")
                or campaign.get("url")
            )
            
            if offer_url:
                logger.info(f"[PRELANDER] Campaign URL before cleaning: {offer_url}")
            else:
                logger.warning(f"[PRELANDER] Campaign {campaign_name} has no URL in any field (default_offer_url, offer_url, url)")
            
            if not password:
                password = campaign.get("password")

    if not offer_url:
        # No campaign found - return a fallback URL with clear message
        # This should rarely happen in production (requires NO active campaigns)
        logger.warning("[PRELANDER] No active campaign found or campaign has no URL, using fallback")
        offer_url = "https://example.com/campaign-not-configured"

    # Spec (Bypass OFF): the visitor ALWAYS lands on the landing page — even
    # when no active template exists. The page falls back to the built-in
    # layout instead of forwarding the visitor to the campaign URL. Skipping
    # the prelander entirely is reserved for Bypass ON, which is handled
    # upstream (traffic_router / resolve_slug) and never reaches this point.
    if is_prelander_host and template_doc is None:
        logger.info(
            "[PRELANDER] No active template for host=%s — rendering built-in "
            "landing page fallback (bypass is OFF: landing page always shows)",
            host,
        )
        return {
            "success": True,
            "offer_url": offer_url,
            "password": password,
            "campaign_name": campaign_name,
            "os": os_lower,
            "template": None,
        }

    response = {
        "success": True,
        "file_name": file_name,
        "file_ext": file_ext,
        "file_size": file_size,
        "file_version": file_version,
        "file_description": file_description,
        "offer_url": offer_url,
        "password": password,
        "campaign_name": campaign_name,
        "os": os_lower,
    }

    # Surface the resolved template's customisable fields so the /d/[slug] page
    # renders the assigned template instead of hard-coded copy. A template with
    # a full_html_template must still be rendered server-side (shortcode
    # substitution), so the router passes the raw fields and the page only uses
    # the simple customisation props.
    if template_doc:
        response["template"] = {
            "id": str(template_doc.get("_id")),
            "name": template_doc.get("name"),
            "os_type": template_doc.get("os_type"),
            "title": template_doc.get("title"),
            "subtitle": template_doc.get("subtitle"),
            "button_text": template_doc.get("button_text"),
            "show_password_field": bool(template_doc.get("show_password_field", True)),
            "show_video": bool(template_doc.get("show_video", False)),
            "video_url": template_doc.get("video_url"),
        }

        # Spec (Prelander Templates → HTML): when the admin pasted a complete
        # HTML template, it is rendered server-side with the applicable
        # campaign URL substituted for {Campaign_URL} and the Password/text
        # content substituted for {Password}. Either, both, or neither
        # shortcode may appear — the engine leaves missing values empty.
        # Render failure falls back to the simple customisation fields above.
        if template_doc.get("full_html_template"):
            from app.services.prelander_service import PrelanderTemplateEngine, RedirectContext
            try:
                ctx = RedirectContext(
                    click_id=str(offer_id or campaign_id or ""),
                    campaign_url=offer_url or "",
                    os=os_lower,
                    password=password or "",
                )
                response["rendered_html"] = PrelanderTemplateEngine().render(
                    template_doc["full_html_template"], ctx
                )
            except Exception as e:
                logger.warning("[PRELANDER] Server-side template render failed: %s", e)
    return response
