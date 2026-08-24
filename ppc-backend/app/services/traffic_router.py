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
    Core traffic routing engine.
    Full flow:
    1. Resolve publisher & website
    2. Campaign match (website-assigned or weighted random)
    3. Direct redirect mode check
    4. GEO rules
    5. Device/OS rules
    6. Landing page or offer selection
    Returns (destination_url, referrer_suppression).
    """
    publisher_id = click_data.get("publisher_id")
    website_id = click_data.get("website_id")
    country_code = click_data.get("country_code")
    device_type = click_data.get("device_type", "desktop")
    os_name = click_data.get("os")

    # --- Step 3: Resolve publisher & website ---
    publisher = None
    if publisher_id:
        publisher = await db.publishers.find_one({"_id": publisher_id})
    if not publisher:
        # Try as ObjectId fallback
        try:
            from bson import ObjectId
            publisher = await db.publishers.find_one({"_id": ObjectId(publisher_id)})
        except Exception:
            pass

    website = None
    if website_id:
        website = await db.websites.find_one({"_id": website_id})
        if not website:
            try:
                from bson import ObjectId
                website = await db.websites.find_one({"_id": ObjectId(website_id)})
            except Exception:
                pass

    # --- Step 4: Campaign match ---
    campaign = None
    if website and website.get("assigned_campaign_id"):
        campaign = await db.campaigns.find_one({
            "_id": website["assigned_campaign_id"],
            "status": "active",
        })

    if not campaign:
        # Try device-OS specific campaign first, then "global" fallback
        os_map = {"windows": "windows", "mac os": "mac", "mac os x": "mac", "macos": "mac", "ios": "mac", "android": "android", "linux": "windows"}
        mapped_os = os_map.get((os_name or "").lower())
        if mapped_os:
            campaign = await db.campaigns.find_one({"device_os": mapped_os, "status": "active"})
        if not campaign:
            # Fallback to "global" campaign (works for all OS)
            campaign = await db.campaigns.find_one({"device_os": "global", "status": "active"})
        if not campaign:
            # Weighted random from all active campaigns
            campaigns = await db.campaigns.find({"status": "active"}).to_list(length=None)
            if campaigns:
                campaign = select_weighted_campaign(campaigns)

    if not campaign:
        # Global default offer URL
        setting = await db.system_settings.find_one({"key": "global_default_offer_url"})
        if setting:
            return setting["value"], False
        return FALLBACK_URL, False

    campaign_id = str(campaign.get("_id", campaign.get("id", "")))
    referrer_suppression = bool(campaign.get("referrer_suppression", False))
    logger.warning(f"[ROUTE] Matched campaign: id={campaign_id}, name={campaign.get('name')}, device_os={campaign.get('device_os')}, os_name={os_name}")

    # --- Step 5: Resolve the final offer URL (GEO > Device > Offer > Campaign default) ---
    resolved_offer_url = None

    # GEO rules — country-specific URL
    if country_code:
        geo_rule = await db.geo_rules.find_one(
            {"campaign_id": campaign_id, "country_code": country_code},
            sort=[("priority", -1)],
        )
        if geo_rule and geo_rule.get("offer_url"):
            logger.warning(f"[ROUTE] GEO rule matched: country={country_code}, url={geo_rule['offer_url']}")
            resolved_offer_url = geo_rule["offer_url"]

    # Device/OS rules
    if not resolved_offer_url:
        device_result = await apply_device_rules(campaign_id, device_type, os_name, db)
        if device_result:
            lander_url, offer_url = device_result
            if offer_url:
                logger.warning(f"[ROUTE] Device rule matched (offer): device={device_type}, os={os_name}")
                resolved_offer_url = offer_url

    # Offer matching
    offer = await find_matching_offer(campaign_id, publisher_id, website_id, os_name, country_code, db)
    if offer:
        logger.warning(f"[ROUTE] Matched offer: id={offer.get('id')}, name={offer.get('name')}, url={offer.get('offer_url')}")
        if not resolved_offer_url:
            resolved_offer_url = offer.get("offer_url")

    # Campaign default
    if not resolved_offer_url:
        resolved_offer_url = campaign.get("default_offer_url", FALLBACK_URL)

    # --- Step 6: Direct redirect check — if ON, skip prelander ---
    if offer and offer.get("direct_redirect_mode"):
        logger.warning(f"[ROUTE] Offer direct redirect ON — bypassing prelander")
        return resolved_offer_url, referrer_suppression

    if campaign.get("direct_redirect_mode"):
        logger.warning(f"[ROUTE] Campaign direct redirect ON — bypassing prelander")
        return resolved_offer_url, referrer_suppression

    # --- Step 7: Show prelander/landing page (direct redirect is OFF) ---
    os_param = "mac" if (os_name or "").lower() in ("mac os", "mac os x", "macos", "ios") else "windows"

    # Match campaign_id whether stored as string or ObjectId in MongoDB.
    campaign_filter = campaign_id_filter(campaign_id)
    landing_pages = await db.landing_pages.find({
        **campaign_filter,
        "status": "active",
    }).to_list(length=100)

    # Fall back to unassigned (global) landing pages only when none are bound
    # to this campaign — keeps weighted rotation working for legacy data.
    if not landing_pages:
        landing_pages = await db.landing_pages.find({
            "status": "active",
            "$or": [
                {"campaign_id": None},
                {"campaign_id": {"$exists": False}},
                {"campaign_id": ""},
            ],
        }).to_list(length=100)

    # Distribute traffic across the campaign's active landing pages by weight.
    landing_page = select_weighted_landing_page(landing_pages)

    from app.services.domain_service import resolve_domain_url, domain_to_url, normalize_domain
    publisher_id = click_data.get("publisher_id")
    last_base = await resolve_domain_url(db, "last", publisher_id)
    intermediate_base = await resolve_domain_url(db, "intermediate", publisher_id)
    has_managed_domain = bool(last_base or intermediate_base)

    if landing_page and (landing_page.get("lander_url") or has_managed_domain):

        # Template page lives on Last Domain when configured, otherwise Intermediate,
        # otherwise the landing page's configured lander_url (legacy).
        # Per-page lander_url takes priority so weighted rotation can send
        # traffic to different domains; managed domains are the fallback.
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
        offer_id = offer.get("id", "") if offer else ""
        cc = country_code or ""
        raw = f"{os_param}:{ts}:{offer_id}:{campaign_id}:{cc}"
        # XOR with key then base64url encode
        key = "mxp2026"
        xored = bytes(ord(c) ^ ord(key[i % len(key)]) for i, c in enumerate(raw))
        slug = base64.urlsafe_b64encode(xored).decode().rstrip("=")
        prelander_dest = f"{template_base}/d/{slug}"
        logger.warning(f"[ROUTE] Sending to prelander: {prelander_dest}")
        return prelander_dest, referrer_suppression

    # --- Fallback: no prelander found, go directly to offer URL ---
    return resolved_offer_url, referrer_suppression


async def find_matching_offer(
    campaign_id: str,
    publisher_id: Optional[str],
    website_id: Optional[str],
    os_name: Optional[str],
    country_code: Optional[str],
    db,
) -> Optional[dict]:
    """
    Find the best matching active offer for the given campaign and click context.
    Offers with more specific targeting are preferred.
    """
    # Eligible offers = those bound to this campaign PLUS "All Campaigns" offers
    # (campaign_id null / unset), which the admin UI exposes as a wildcard.
    cid_filter = campaign_id_filter(campaign_id)
    offers = await db.offers.find({
        "status": "active",
        "$or": [
            cid_filter,
            {"campaign_id": None},
            {"campaign_id": {"$exists": False}},
        ],
    }).to_list(length=100)

    if not offers:
        return None

    # Normalize OS name for matching
    os_map = {"windows": "windows", "mac os": "mac", "mac os x": "mac", "macos": "mac", "ios": "mac", "android": "android", "linux": "windows"}
    mapped_os = os_map.get((os_name or "").lower(), (os_name or "").lower())

    best_offer = None
    best_score = -1

    for o in offers:
        o["id"] = str(o.get("_id", ""))
        score = 0

        # Check OS targeting
        os_types = o.get("os_types", [])
        if os_types:
            if mapped_os not in [t.lower() for t in os_types]:
                continue  # OS doesn't match, skip
            score += 1

        # Check country targeting
        country_codes = o.get("country_codes", [])
        if country_codes:
            if not country_code or country_code.upper() not in [c.upper() for c in country_codes]:
                continue  # Country doesn't match, skip
            score += 1

        # Check publisher targeting (compare as strings — ids may be str or ObjectId)
        pub_ids = o.get("publisher_ids", [])
        if pub_ids:
            norm_pubs = {normalize_id(pid) for pid in pub_ids}
            if not publisher_id or normalize_id(publisher_id) not in norm_pubs:
                continue  # Publisher doesn't match, skip
            score += 1

        # Check website targeting
        web_ids = o.get("website_ids", [])
        if web_ids:
            norm_webs = {normalize_id(wid) for wid in web_ids}
            if not website_id or normalize_id(website_id) not in norm_webs:
                continue  # Website doesn't match, skip
            score += 1

        if score > best_score:
            best_score = score
            best_offer = o

    return best_offer


async def apply_geo_rules(campaign_id: str, country_code: str, db) -> Optional[str]:
    """Find best matching GEO rule for the given country."""
    rule = await db.geo_rules.find_one(
        {"campaign_id": campaign_id, "country_code": country_code},
        sort=[("priority", -1)],
    )
    if rule:
        return rule.get("offer_url")
    return None


async def apply_device_rules(
    campaign_id: str, device_type: str, os_name: Optional[str], db
) -> Optional[Tuple[Optional[str], Optional[str]]]:
    """
    Find best matching device rule.
    Returns (lander_url, offer_url) or None.
    """
    # Try OS-specific match first
    if os_name:
        rule = await db.device_rules.find_one(
            {
                "campaign_id": campaign_id,
                "device_type": device_type,
                "os": os_name,
            },
            sort=[("priority", -1)],
        )
        if rule:
            return rule.get("lander_url"), rule.get("offer_url")

    # Fall back to device_type only match
    rule = await db.device_rules.find_one(
        {
            "campaign_id": campaign_id,
            "device_type": device_type,
            "$or": [{"os": None}, {"os": {"$exists": False}}, {"os": ""}],
        },
        sort=[("priority", -1)],
    )
    if rule:
        return rule.get("lander_url"), rule.get("offer_url")

    return None
