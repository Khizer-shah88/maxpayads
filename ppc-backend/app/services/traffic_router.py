from typing import Optional, Tuple
from app.services.campaign_service import get_campaign_for_website, select_weighted_campaign
from app.utils.db_utils import campaign_id_filter, normalize_id
from app.core.constants import DOMAIN_TYPE_INTER, DOMAIN_TYPE_PRELANDER
from app.models.redirect_chain import chain_inter_domain, chain_prelander_pool
import logging
import time
import base64

logger = logging.getLogger(__name__)

FALLBACK_URL = "https://example.com"


def _record(ctx, stage: str, outcome: str, **detail) -> None:
    """
    Record a routing decision on the pipeline context, when one was passed.

    `route_click` is also called without a context (ad server, tests), so every
    call site has to tolerate `ctx=None`.
    """
    if ctx is not None:
        ctx.record(stage, outcome, **detail)


def _clean_campaign_url(url: str) -> str:
    """
    Clean campaign URL to ensure it's properly formatted.
    
    Fixes common issues:
    - Removes accidental domain prefixes like: https://domain.com/https/actualurl.com
    - Ensures proper https:// or http:// protocol
    - Handles malformed URLs from database
    
    Examples:
        https://clicksetopfile.cc/https/examplewin.com → https://examplewin.com
        https://domain.com/http/example.com → http://example.com
        examplewin.com → https://examplewin.com
    """
    if not url:
        return FALLBACK_URL
    
    # Remove any trailing/leading whitespace
    url = url.strip()
    
    # Check if URL has a domain prefix followed by /https/ or /http/
    # Pattern: https://somedomain.com/https/actualurl.com
    if "/https/" in url:
        # Extract everything after /https/
        parts = url.split("/https/")
        if len(parts) > 1:
            url = "https://" + parts[-1]
            logger.info(f"[URL CLEAN] Removed domain prefix, extracted: {url}")
    
    elif "/http/" in url:
        # Extract everything after /http/
        parts = url.split("/http/")
        if len(parts) > 1:
            url = "http://" + parts[-1]
            logger.info(f"[URL CLEAN] Removed domain prefix, extracted: {url}")
    
    # Ensure URL starts with http:// or https://
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
        logger.info(f"[URL CLEAN] Added https:// protocol: {url}")
    
    # Final validation
    if not url.startswith(("http://", "https://")):
        logger.warning(f"[URL CLEAN] Invalid URL after cleaning: {url}, using fallback")
        return FALLBACK_URL
    
    return url


def _absolute_base(url: Optional[str]) -> Optional[str]:
    """
    Force a resolved domain base to an absolute https:// URL (no trailing /).

    A bare hostname ("clicklyspot.icu") coming from any resolution path would
    make the /d/{slug} destination RELATIVE — the browser resolves it against
    the publisher's page and the visitor lands on
    https://publisher.com/clicklyspot.icu/d/{slug} (404, flow dead). This
    guard guarantees that can never happen again, whatever the DB contains.
    """
    if not url:
        return None
    from app.services.domain_service import normalize_domain
    host = normalize_domain(url)
    if not host:
        return None
    return f"https://{host}"


def slug_os_param(os_name: Optional[str]) -> str:
    """
    The OS value embedded in the encrypted prelander slug.

    Resolved through the shared glossary normalizer so variant spellings
    ("OS X", "iPhone", "Darwin", …) map consistently with targeting and the
    prelander lookup. The slug OS stays in {windows, mac} because those are
    the only two layouts the /d/[slug] page renders — everything else, and
    any unrecognised value, falls to the windows layout.
    """
    from app.core.glossary import normalize_os
    return "mac" if normalize_os(os_name, default="windows") == "mac" else "windows"


def build_prelander_slug(
    os_param: str,
    campaign_id,
    offer_id: str = "",
    country_code: Optional[str] = None,
) -> str:
    """
    Encrypted slug carrying {os, timestamp, offer_id, campaign_id, country}.

    The Intermediate domain's /d/[slug] page decodes it (prelander_router) to
    decide the next hop: bypass OFF → Prelander landing page, bypass ON →
    Campaign URL. Same XOR recipe the prelander side decrypts with.
    """
    ts = str(int(time.time()))
    raw = f"{os_param}:{ts}:{offer_id or ''}:{campaign_id or ''}:{country_code or ''}"
    key = "mxp2026"
    xored = bytes(ord(c) ^ ord(key[i % len(key)]) for i, c in enumerate(raw))
    return base64.urlsafe_b64encode(xored).decode().rstrip("=")


async def resolve_active_chain(db, publisher_id: Optional[str], request_host: Optional[str] = None) -> Optional[dict]:
    """
    Resolve the admin-configured Redirection Chain for a click.

    DOMAIN-SPECIFIC RULE: chains are strictly tied to their Anchor domain. A
    chain ONLY applies when traffic enters through its specified Anchor domain
    (global publisher rule preserved: a matched chain applies to ALL
    publishers — publisher identity never determines chain ownership).

    Resolution:
    - request_host matches a chain's anchor_domain → that chain
    - no match → None (default domain routing applies instead)

    The stored anchor hostname is normalized on both sides, so chains saved
    with protocol/case variants still match the incoming host.
    """
    try:
        from app.services.domain_service import normalize_domain

        if not request_host:
            # No host specified - cannot match a chain
            return None

        host = normalize_domain(request_host)
        if not host:
            return None

        # Direct anchor match first (fast path)
        chain = await db.redirect_chains.find_one({
            "anchor_domain": host,
            "status": "active",
        })

        if not chain:
            # Chains may store the domain with protocol/case variants —
            # normalize both sides before deciding there is no match.
            chains = await db.redirect_chains.find({"status": "active"}).to_list(length=200)
            chain = next(
                (
                    c for c in chains
                    if normalize_domain(c.get("anchor_domain")) == host
                ),
                None,
            )

        if chain:
            logger.info(f"[CHAIN] Matched chain '{chain.get('name')}' for anchor domain: {host}")
            return chain

        # No chain for this domain - will use default domain routing
        logger.debug(f"[CHAIN] No chain configured for domain: {host}")
        return None
    except Exception as e:
        logger.warning("[CHAIN] Resolution failed: %s", e)
        return None


def chain_extra_hops(chain: Optional[dict]) -> list:
    """
    The ordered extra hops configured on a chain (Anchor → Inter → C → D → …).

    `extra_domains` is the canonical key; older chains carry none, which simply
    means the flow is Anchor → Inter → Prelander Pool.
    """
    if not chain:
        return []
    return [d for d in (chain.get("extra_domains") or []) if d]


def chain_hop_sequence(chain: Optional[dict]) -> list:
    """
    The full managed hop sequence for a chain AFTER the Inter domain, in order:
    every extra hop, then nothing (the Prelander pool entry is resolved by the
    caller — chain_prelander_pool provides candidates, not a single domain).
    """
    return chain_extra_hops(chain)


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


async def find_matching_offer(
    campaign_id,
    publisher_id: Optional[str],
    website_id: Optional[str],
    os_name: Optional[str],
    country_code: Optional[str],
    db,
    device_type: Optional[str] = "desktop",
) -> Optional[dict]:
    """
    Resolve the single most-specific eligible Offer for this click.

    Re-added after the Phase 3 targeting-engine refactor removed the original
    implementation — `app.tasks.click_tasks` still calls this to pick up an
    Offer's own CPC for the background settlement. Delegates entirely to the
    centralized TargetingEngine so offer eligibility (publisher, website,
    country, OS) can never drift between routing and CPC resolution.

    Returns the winning offer document (with cpc/payout) or None.
    """
    from app.services.targeting_engine import TargetingEngine, ClickContext

    if not campaign_id:
        return None

    context = ClickContext(
        publisher_id=publisher_id,
        website_id=website_id,
        country_code=country_code,
        device_type=device_type,
        os=os_name,
        campaign_id=str(campaign_id),
    )

    engine = TargetingEngine(db)
    _url, _supp, metadata = await engine.resolve_destination(context)

    if metadata.get("rule_type") != "offer" or not metadata.get("source_id"):
        return None

    try:
        from bson import ObjectId as OId

        offer = await db.offers.find_one({"_id": OId(metadata["source_id"])})
    except Exception:
        offer = await db.offers.find_one({"_id": metadata["source_id"]})
    return offer or None


async def route_click(click_data: dict, db, redis, ctx=None) -> Tuple[str, bool]:
    """
    Core traffic routing engine - USES CENTRALIZED TARGETING ENGINE.
    
    Traffic Routing Flow Based on Bypass Status:
    
    BYPASS OFF (default):
        Publisher Smartlink → Anchor Domain → Inter Domain → Logs → Prelander Domain
        - The final destination is a prelander page on the Prelander domain
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

    When `ctx` is a RedirectResolutionContext, each decision below is recorded on
    it. The trace follows execution order, not the order the stages are listed
    in: chain domains are resolved lazily, so on the bypass path the chain stage
    reports "not_needed_bypass" instead of doing the lookups.
    """
    from app.services.redirect_pipeline import (
        STAGE_CAMPAIGN, STAGE_CHAIN, STAGE_OFFER, STAGE_PRELANDER,
    )
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
            _record(ctx, STAGE_CAMPAIGN, "none_global_default", url=setting["value"])
            return setting["value"], False
        _record(ctx, STAGE_CAMPAIGN, "none_hardcoded_fallback", url=FALLBACK_URL)
        return FALLBACK_URL, False
    
    logger.info(f"[ROUTE] Matched campaign_id: {campaign_id}")
    if ctx is not None:
        ctx.campaign_id = str(campaign_id)
    _record(ctx, STAGE_CAMPAIGN, "matched", campaign_id=str(campaign_id))
    
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
    if ctx is not None:
        ctx.offer_url = resolved_offer_url
        ctx.referrer_suppression = referrer_suppression
        ctx.targeting_rule_type = metadata.get("rule_type")
        if metadata.get("rule_type") == "offer":
            ctx.offer_id = metadata.get("source_id")
    _record(
        ctx, STAGE_OFFER, metadata.get("rule_type") or "unmatched",
        url=resolved_offer_url,
        priority=metadata.get("priority"),
        source_id=metadata.get("source_id"),
        matched_criteria=metadata.get("matched_criteria"),
        rules_evaluated=metadata.get("total_rules_evaluated"),
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
    bypass_source = None
    try:
        from bson import ObjectId
        campaign_oid = ObjectId(campaign_id) if isinstance(campaign_id, str) else campaign_id
        campaign = await db.campaigns.find_one({"_id": campaign_oid})
        if campaign and campaign.get("direct_redirect_mode"):
            is_bypass_on = True
            bypass_source = "campaign"
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
                bypass_source = "offer"
                logger.info("[ROUTE] Bypass ON (offer) — will skip prelander, go direct to campaign URL")
        except Exception:
            pass

    # ── Chain override (domain mapping only) ──────────────────────────────────
    # The Redirection Chain Builder is a DOMAIN-LEVEL OVERRIDE: an active chain
    # whose Anchor domain IS the host /click ran on redefines where this
    # domain's traffic goes (Inter → extra hops → Prelander pool). No chain
    # for this anchor → the DEFAULT redirection-domain flow stays exactly as
    # is (publisher-assigned → global default → active pool).
    # Every chain domain is forced to an absolute https:// URL — a bare
    # hostname in a chain field would build a RELATIVE /d/{slug} destination
    # and the browser would resolve it against the publisher's page.
    chain = await resolve_active_chain(
        db, publisher_id, getattr(ctx, "request_host", None) if ctx is not None else None,
    )
    if ctx is not None:
        ctx.redirect_chain = chain
    chain_inter = _absolute_base(chain_inter_domain(chain)) if chain else None
    chain_pool: list = []
    if chain:
        for d in chain_prelander_pool(chain):
            base = _absolute_base(d)
            if base:
                chain_pool.append(base)
    chain_hops: list = []
    if chain:
        for d in chain_extra_hops(chain):
            base = _absolute_base(d)
            if base:
                chain_hops.append(base)

    if is_bypass_on:
        clean_url = _clean_campaign_url(resolved_offer_url)
        if ctx is not None:
            ctx.skip_prelander = True
            ctx.bypass_url = clean_url
        
        # Spec flow (Bypass ON): Anchor (Smartlink host) → Inter /d/{slug}
        # (0.75s loader) → Campaign URL. The /d page on the Inter domain reads
        # bypass_redirect_url from /domain-type and goes straight to the
        # Campaign URL — the landing page is never shown. The first hop built
        # here is the INTER domain; the anchor is the domain /click already ran
        # on, so sending the visitor back there loops on the same domain.
        entry_base = chain_inter
        if not entry_base:
            try:
                from app.services.domain_service import resolve_domain_url
                resolved_inter = await resolve_domain_url(db, DOMAIN_TYPE_INTER, publisher_id)
                if resolved_inter:
                    entry_base = _absolute_base(resolved_inter)
            except Exception:
                pass
        
        if entry_base:
            os_param_b = slug_os_param(os_name)
            offer_id_b = metadata.get("source_id", "") if metadata.get("rule_type") == "offer" else ""
            slug_b = build_prelander_slug(os_param_b, str(campaign_id), offer_id_b, country_code)
            dest = f"{entry_base}/d/{slug_b}"
            logger.info("[ROUTE] BYPASS ON: via Inter %s → campaign %s", dest, clean_url)
            if ctx is not None:
                ctx.inter_url = entry_base
            _record(
                ctx, STAGE_CHAIN, "resolved_bypass_inter",
                inter=entry_base, chain=(chain or {}).get("name"),
                extra_hops=len(chain_hops),
            )
            _record(ctx, STAGE_PRELANDER, "skipped_bypass_via_inter", source=bypass_source, url=clean_url, inter=entry_base)
            return dest, referrer_suppression
        logger.info(f"[ROUTE] BYPASS ON, no inter domain: direct to campaign URL: {clean_url}")
        _record(ctx, STAGE_CHAIN, "not_needed_bypass")
        _record(ctx, STAGE_PRELANDER, "skipped_bypass", source=bypass_source, url=clean_url)
        return clean_url, referrer_suppression
    
    # --- Step 5: Build prelander destination URL ---
    # Bypass OFF: Build prelander URL with encrypted slug
    # The traffic flow is: Anchor → Inter → Prelander Domain (last)
    # 
    # Note: The anchor and inter domains handle session cookies and logging.
    # This function generates the prelander URL that will be the final destination
    # after passing through those domains.
    
    logger.info("[ROUTE] BYPASS OFF: Building prelander destination")
    
    os_param = slug_os_param(os_name)

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

    from app.core.glossary import domain_type_filter
    from app.services.domain_service import (
        resolve_domain_url, domain_to_url, normalize_domain,
        select_active_prelander,
    )
    # Prelander resolution — chain override first, default flow untouched:
    # 1. Chain matched (anchor host mapping): its Prelander pool (weighted
    #    pick among ACTIVE domains) is the final landing page source, its
    #    extra hops follow the Inter.
    # 2. No chain: classic redirection-domain flow (publisher-assigned →
    #    global default → active pool by weight).
    if chain_pool:
        weighted_chain_pick = await select_active_prelander(
            db, [normalize_domain(b) for b in chain_pool]
        )
        last_base = _absolute_base(weighted_chain_pick) if weighted_chain_pick else None
        if not last_base:
            from app.services.redirect_pipeline import FALLBACK_URL
            return FALLBACK_URL, referrer_suppression
    else:
        publisher_prelander = await resolve_domain_url(db, DOMAIN_TYPE_PRELANDER, publisher_id) if publisher_id else None
        if publisher_prelander:
            last_base = publisher_prelander
        else:
            prelander_filter = domain_type_filter(DOMAIN_TYPE_PRELANDER)
            pool_docs = await db.redirection_domains.find({
                "domain_type": prelander_filter,
                "status": "active",
            }).to_list(length=200)
            weighted_pick = await select_active_prelander(
                db, [d.get("domain") for d in pool_docs]
            )
            last_base = domain_to_url(weighted_pick) if weighted_pick else await resolve_domain_url(db, DOMAIN_TYPE_PRELANDER, None)
    intermediate_base = chain_inter or await resolve_domain_url(db, DOMAIN_TYPE_INTER, publisher_id)
    # Guard every resolved base: bare hostnames must never reach the /d URL
    # builders (they would produce a RELATIVE destination → visitor 404s on
    # https://publisher.com/<hostname>/d/{slug}).
    last_base = _absolute_base(last_base)
    intermediate_base = _absolute_base(intermediate_base)
    has_managed_domain = bool(last_base or intermediate_base or chain_hops)

    if ctx is not None:
        ctx.prelander_url = last_base
        ctx.inter_url = intermediate_base
        ctx.anchor_url = getattr(ctx, "request_host", None)
    _record(
        ctx, STAGE_CHAIN,
        "resolved" if has_managed_domain else "no_managed_domain",
        anchor=getattr(ctx, "request_host", None) if ctx is not None else None,
        inter=intermediate_base,
        prelander=last_base,
        chain=(chain or {}).get("name"),
        extra_hops=len(chain_hops),
        landing_pages_considered=len(landing_pages),
    )

    if has_managed_domain or (landing_page and landing_page.get("lander_url")):
        legacy_lander = (landing_page.get("lander_url") if landing_page else "") or ""
        lander_url = (legacy_lander or last_base or intermediate_base or "").strip().rstrip("/")
        # A lander_url stored as a bare hostname must become absolute too —
        # same relative-destination failure mode as the domain bases.
        if lander_url and not lander_url.startswith(("http://", "https://")):
            lander_url = _absolute_base(lander_url) or ""
        if not lander_url:
            logger.warning("[ROUTE] No valid lander URL, falling back to campaign URL")
            _record(ctx, STAGE_PRELANDER, "skipped_no_lander_url", url=resolved_offer_url)
            return resolved_offer_url, referrer_suppression

        # Entry point for the prelander hop. Spec flow (Bypass OFF):
        #   Anchor (Smartlink host, /click runs here) → Inter /d/{slug} (0.75s
        #   loader) → [chain extra hops] → Landing Page.
        # The visitor is ALREADY on the Anchor domain — /click executes there —
        # so the first hop this router builds must be the INTER domain, never
        # the anchor again (sending them to anchor/d/{slug} loops on the same
        # domain). Only when no Inter domain exists does the visitor enter on
        # the first chain extra hop, the Prelander domain, or the legacy lander.
        if intermediate_base:
            entry_domain = intermediate_base.rstrip("/")
            logger.info("[ROUTE] Inter domain (entry): %s", entry_domain)
        elif chain_hops:
            entry_domain = chain_hops[0].rstrip("/")
            logger.info("[ROUTE] No inter configured, entering on first chain hop: %s", entry_domain)
        elif last_base:
            entry_domain = last_base.rstrip("/")
            logger.info("[ROUTE] No inter domain configured, entering on prelander: %s", entry_domain)
        else:
            entry_domain = lander_url.rstrip("/")
            logger.info("[ROUTE] Using legacy lander URL: %s", entry_domain)

        # Final guard: the /d/{slug} destination must be an absolute URL.
        # Whatever produced the entry (pool pick, legacy setting, lander
        # field), a protocol-less value here kills the whole flow with a
        # relative redirect.
        entry_domain = _absolute_base(entry_domain)
        if not entry_domain:
            logger.warning("[ROUTE] No absolute entry domain, falling back to campaign URL")
            _record(ctx, STAGE_PRELANDER, "skipped_no_lander_url", url=resolved_offer_url)
            return resolved_offer_url, referrer_suppression

        # Generate encrypted slug containing campaign data
        # This slug is decoded on the inter/prelander page to show the
        # appropriate template and eventually redirect to the campaign URL
        offer_id = metadata.get("source_id", "") if metadata.get("rule_type") == "offer" else ""
        slug = build_prelander_slug(os_param, campaign_id, offer_id, country_code)
        prelander_dest = f"{entry_domain}/d/{slug}"
        logger.info("[ROUTE] Final prelander URL: %s", prelander_dest)
        _record(
            ctx, STAGE_PRELANDER, "prelander",
            entry_domain=entry_domain,
            entry_type=(
                "inter" if intermediate_base
                else "chain_hop" if (chain_hops and not last_base)
                else "prelander" if last_base
                else "legacy_lander"
            ),
            remaining_hops=len(chain_hops),
            os_param=os_param,
            offer_id=offer_id or None,
        )
        return prelander_dest, referrer_suppression

    # No prelander configured — fall back to campaign URL
    logger.info("[ROUTE] No prelander domain configured, falling back to campaign URL")
    _record(ctx, STAGE_PRELANDER, "skipped_none_configured", url=resolved_offer_url)
    return resolved_offer_url, referrer_suppression



