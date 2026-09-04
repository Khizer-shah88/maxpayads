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
    
    Traffic Routing Flow Based on Bypass Status:
    
    BYPASS OFF (default):
        Publisher Smartlink → Anchor Domain → Inter Domain → Logs → Prelander Domain
        - The final destination is a prelander page on the "last" domain
        - User sees the prelander template before reaching the campaign URL
    
    BYPASS ON (direct_redirect_mode=True):
        Publisher Smartlink → Anchor Domain → Inter Domain → Logs → Direct Campaign URL
        - The prelander is completely skipped
        - User goes directly to the campaign/offer URL
        - Still passes through anchor/inter domains for logging
    
    Steps:
    1. Resolve campaign for click
    2. Build click context
    3. Use TargetingEngine to resolve destination (all rules centralized)
    4. Check bypass status (direct_redirect_mode on campaign or offer)
    5. Return direct campaign URL (if bypass ON) or prelander URL (if bypass OFF)
    
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
    
    # --- Step 4: Check direct redirect mode (Bypass) ---
    # This determines the final destination after passing through anchor and inter domains
    # 
    # Flow with Bypass OFF (default):
    #   Publisher Smartlink → Anchor Domain → Inter Domain → Logs → Prelander Domain
    # 
    # Flow with Bypass ON:
    #   Publisher Smartlink → Anchor Domain → Inter Domain → Logs → Direct Campaign URL
    # 
    # NOTE: The anchor and inter domains are handled externally (middleware/click endpoint).
    # This function only determines what URL to send as the FINAL destination.
    is_bypass_on = False
    try:
        from bson import ObjectId
        campaign_oid = ObjectId(campaign_id) if isinstance(campaign_id, str) else campaign_id
        campaign = await db.campaigns.find_one({"_id": campaign_oid})
        if campaign and campaign.get("direct_redirect_mode"):
            is_bypass_on = True
            logger.info("[ROUTE] Bypass ON (campaign) — will skip prelander, go direct to campaign URL")
    except Exception as e:
        logger.debug("[ROUTE] Campaign bypass lookup failed: %s", e)

    # Also check matched offer for bypass setting
    if not is_bypass_on and metadata.get("rule_type") == "offer" and metadata.get("source_id"):
        try:
            from bson import ObjectId as OId
            offer = await db.offers.find_one({"_id": OId(metadata["source_id"])})
            if offer and offer.get("direct_redirect_mode"):
                is_bypass_on = True
                logger.info("[ROUTE] Bypass ON (offer) — will skip prelander, go direct to campaign URL")
        except Exception:
            pass

    # Bypass ON: Return the campaign/offer URL directly (skip prelander)
    # The traffic still goes through anchor → inter domain for logging, 
    # but the final destination is the campaign URL, not the prelander
    if is_bypass_on:
        logger.info(f"[ROUTE] BYPASS MODE: Direct to campaign URL: {resolved_offer_url}")
        return resolved_offer_url, referrer_suppression
    
    # --- Step 5: Build prelander destination URL ---
    # Bypass OFF: Build prelander URL with encrypted slug
    # The traffic flow is: Anchor → Inter → Prelander Domain (last)
    # 
    # Note: The anchor and inter domains handle session cookies and logging.
    # This function generates the prelander URL that will be the final destination
    # after passing through those domains.
    
    logger.info("[ROUTE] BYPASS OFF: Building prelander destination")
    
    os_param = "mac" if (os_name or "").lower() in ("mac os", "mac os x", "macos", "ios") else "windows"

    campaign_filter = campaign_id_filter(campaign_id)
    landing_pages = await db.landing_pages.find({
        **campaign_filter,
        "status": "active",
    }).to_list(length=100)

    if not landing_pages:
        landing_pages = await db.landing_pages.find({
            "status": "active",
            "$or": [
                {"campaign_id": None},
                {"campaign_id": {"$exists": False}},
                {"campaign_id": ""},
            ],
        }).to_list(length=100)

    landing_page = select_weighted_landing_page(landing_pages)

    from app.services.domain_service import resolve_domain_url, domain_to_url, normalize_domain
    last_base = await resolve_domain_url(db, "last", publisher_id)
    intermediate_base = await resolve_domain_url(db, "intermediate", publisher_id)
    has_managed_domain = bool(last_base or intermediate_base)

    if has_managed_domain or (landing_page and landing_page.get("lander_url")):
        legacy_lander = (landing_page.get("lander_url") if landing_page else "") or ""
        lander_url = (legacy_lander or last_base or intermediate_base or "").strip().rstrip("/")
        if not lander_url.startswith("http"):
            normalized = normalize_domain(lander_url or legacy_lander)
            lander_url = domain_to_url(normalized) if normalized else ""
        if not lander_url:
            logger.warning("[ROUTE] No valid lander URL, falling back to campaign URL")
            return resolved_offer_url, referrer_suppression

        # Use the last (prelander) domain as the final destination
        # The full flow: Publisher → Anchor → Inter → Last Domain (prelander page)
        # The inter domain logs the click before redirecting to the last domain
        if last_base:
            entry_domain = last_base.rstrip("/")
            logger.info("[ROUTE] Prelander domain (last): %s", entry_domain)
        elif intermediate_base:
            entry_domain = intermediate_base.rstrip("/")
            logger.info("[ROUTE] No last domain configured, using intermediate: %s", entry_domain)
        else:
            entry_domain = lander_url.rstrip("/")
            logger.info("[ROUTE] Using legacy lander URL: %s", entry_domain)

        # Generate encrypted slug containing campaign data
        # This slug is decoded on the prelander page to show the appropriate template
        # and eventually redirect to the campaign URL
        ts = str(int(time.time()))
        offer_id = metadata.get("source_id", "") if metadata.get("rule_type") == "offer" else ""
        cc = country_code or ""
        raw = f"{os_param}:{ts}:{offer_id}:{campaign_id}:{cc}"
        key = "mxp2026"
        xored = bytes(ord(c) ^ ord(key[i % len(key)]) for i, c in enumerate(raw))
        slug = base64.urlsafe_b64encode(xored).decode().rstrip("=")
        prelander_dest = f"{entry_domain}/d/{slug}"
        logger.info("[ROUTE] Final prelander URL: %s", prelander_dest)
        return prelander_dest, referrer_suppression

    # No prelander configured — fall back to campaign URL
    logger.info("[ROUTE] No prelander domain configured, falling back to campaign URL")
    return resolved_offer_url, referrer_suppression



