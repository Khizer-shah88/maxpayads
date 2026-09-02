from typing import Optional, Tuple
from app.services.campaign_service import get_campaign_for_website, select_weighted_campaign
from app.utils.db_utils import campaign_id_filter, normalize_id
import logging
import time
import base64

logger = logging.getLogger(__name__)

FALLBACK_URL = "https://example.com"


def select_weighted_landing_page(landing_pages: list) -> Optional[dict]:
    """
    Pick one landing page using weighted random rotation, keyed on each page's
    ``weight`` field. Two pages at weight 50/50 each receive ~half of traffic
    over time; a page with weight 0 is never selected (use it to pause a page
    by weight while keeping it configured). Mirrors ``select_weighted_campaign``.
    """
    import random

    if not landing_pages:
        return None

    weighted = [(lp, max(0, int(lp.get("weight", 100) or 0))) for lp in landing_pages]
    total = sum(w for _, w in weighted)
    if total <= 0:
        # No usable weights configured — fall back to the first page deterministically.
        return landing_pages[0]

    rand = random.uniform(0, total)
    cumulative = 0
    for lp, w in weighted:
        if w <= 0:
            continue
        cumulative += w
        if rand <= cumulative:
            return lp
    # Numerical edge (rand landed past the last positive bucket) — return last positive.
    for lp, w in reversed(weighted):
        if w > 0:
            return lp
    return landing_pages[0]


async def route_click(click_data: dict, db, redis) -> Tuple[str, bool]:
    """
    Core traffic routing engine - USES CENTRALIZED TARGETING ENGINE.
    
    Flow:
    1. Resolve campaign for click
    2. Build click context
    3. Use TargetingEngine to resolve destination (all rules centralized)
    4. Check direct redirect mode
    5. Show prelander if needed
    
    Returns (destination_url, referrer_suppression).
    """
    from app.services.targeting_engine import (
        TargetingEngine,
        ClickContext,
        resolve_campaign_for_click,
    )
    
    publisher_id = click_data.get("publisher_id")
    website_id = click_data.get("website_id")
    country_code = click_data.get("country_code")
    device_type = click_data.get("device_type", "desktop")
    os_name = click_data.get("os")
    
    # --- Step 1: Resolve campaign for this click ---
    campaign_id = await resolve_campaign_for_click(click_data, db)
    
    if not campaign_id:
        logger.warning("[ROUTE] No campaign found, using fallback")
        # Global default offer URL
        setting = await db.system_settings.find_one({"key": "global_default_offer_url"})
        if setting:
            return setting["value"], False
        return FALLBACK_URL, False
    
    logger.info(f"[ROUTE] Matched campaign_id: {campaign_id}")
    
    # --- Step 2: Build click context for targeting engine ---
    context = ClickContext(
        publisher_id=publisher_id,
        website_id=website_id,
        country_code=country_code,
        device_type=device_type,
        os=os_name,
        campaign_id=campaign_id,
    )
    
    # --- Step 3: Use centralized targeting engine to resolve destination ---
    engine = TargetingEngine(db, redis)
    resolved_offer_url, referrer_suppression, metadata = await engine.resolve_destination(context)
    
    logger.info(
        f"[ROUTE] Targeting resolved: url={resolved_offer_url}, "
        f"rule_type={metadata.get('rule_type')}, priority={metadata.get('priority')}"
    )
    
    # --- Step 4: Check direct redirect mode (skip prelander) ---
    campaign = await db.campaigns.find_one({"_id": campaign_id})
    if campaign and campaign.get("direct_redirect_mode"):
        logger.info("[ROUTE] Campaign direct redirect ON — bypassing prelander")
        return resolved_offer_url, referrer_suppression
    
    # Check if matched offer has direct redirect mode
    if metadata.get("rule_type") == "offer" and metadata.get("source_id"):
        try:
            from bson import ObjectId
            offer = await db.offers.find_one({"_id": ObjectId(metadata["source_id"])})
            if offer and offer.get("direct_redirect_mode"):
                logger.info("[ROUTE] Offer direct redirect ON — bypassing prelander")
                return resolved_offer_url, referrer_suppression
        except Exception:
            pass
    
    # --- Step 5: Show prelander/landing page (direct redirect is OFF) ---
    os_param = "mac" if (os_name or "").lower() in ("mac os", "mac os x", "macos", "ios") else "windows"
    
    # Match campaign_id whether stored as string or ObjectId in MongoDB
    campaign_filter = campaign_id_filter(campaign_id)
    landing_pages = await db.landing_pages.find({
        **campaign_filter,
        "status": "active",
    }).to_list(length=100)
    
    # Fall back to unassigned (global) landing pages only when none are bound
    # to this campaign — keeps weighted rotation working for legacy data
    if not landing_pages:
        landing_pages = await db.landing_pages.find({
            "status": "active",
            "$or": [
                {"campaign_id": None},
                {"campaign_id": {"$exists": False}},
                {"campaign_id": ""},
            ],
        }).to_list(length=100)
    
    # Distribute traffic across the campaign's active landing pages by weight
    landing_page = select_weighted_landing_page(landing_pages)
    
    from app.services.domain_service import resolve_domain_url, domain_to_url, normalize_domain
    last_base = await resolve_domain_url(db, "last", publisher_id)
    intermediate_base = await resolve_domain_url(db, "intermediate", publisher_id)
    has_managed_domain = bool(last_base or intermediate_base)
    
    if landing_page and (landing_page.get("lander_url") or has_managed_domain):
        # Template page lives on Last Domain when configured, otherwise Intermediate,
        # otherwise the landing page's configured lander_url (legacy)
        legacy_lander = (landing_page.get("lander_url") or "").strip()
        lander_url = (legacy_lander or last_base or intermediate_base or "").strip().rstrip("/")
        if not lander_url.startswith("http"):
            normalized = normalize_domain(lander_url or legacy_lander)
            lander_url = domain_to_url(normalized) if normalized else ""
        if not lander_url:
            return resolved_offer_url, referrer_suppression
        
        # Optional intermediate hop before the template page (rare three-step flow)
        if intermediate_base and last_base and normalize_domain(intermediate_base) != normalize_domain(last_base):
            lander_url = intermediate_base.rstrip("/")
            template_base = last_base.rstrip("/")
        else:
            template_base = lander_url
        
        # Generate encrypted slug — encodes OS + timestamp + offer_id + campaign_id + country_code
        ts = str(int(time.time()))
        offer_id = metadata.get("source_id", "") if metadata.get("rule_type") == "offer" else ""
        cc = country_code or ""
        raw = f"{os_param}:{ts}:{offer_id}:{campaign_id}:{cc}"
        # XOR with key then base64url encode
        key = "mxp2026"
        xored = bytes(ord(c) ^ ord(key[i % len(key)]) for i, c in enumerate(raw))
        slug = base64.urlsafe_b64encode(xored).decode().rstrip("=")
        prelander_dest = f"{template_base}/d/{slug}"
        logger.info(f"[ROUTE] Sending to prelander: {prelander_dest}")
        return prelander_dest, referrer_suppression
    
    # --- Fallback: no prelander found, go directly to offer URL ---
    logger.info("[ROUTE] No prelander configured, routing directly to offer")
    return resolved_offer_url, referrer_suppression



