"""
Centralized Targeting/Rule Engine
==================================
Single source of truth for all campaign destination resolution.

Priority Order (highest to lowest):
1. Direct Offer Targeting (most specific)
   - Publisher + Website + GEO + OS
2. GEO Rules (country-specific)
3. Device/OS Rules  
4. Campaign Offers (with targeting)
5. Campaign Default URL
6. Global Fallback URL

This engine ensures deterministic, predictable routing with zero logic scatter.
Every redirect goes through resolve_destination().
"""

from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

from app.core.glossary import normalize_os
import logging

logger = logging.getLogger(__name__)

FALLBACK_URL = "https://example.com"


@dataclass
class ClickContext:
    """
    Normalized click context for targeting decisions.
    All fields are optional to support partial matching.
    """
    publisher_id: Optional[str] = None
    website_id: Optional[str] = None
    country_code: Optional[str] = None
    device_type: Optional[str] = None
    os: Optional[str] = None
    campaign_id: Optional[str] = None
    
    # Computed fields
    normalized_os: Optional[str] = None
    
    def __post_init__(self):
        """Resolve the raw OS name onto the fixed OS enum for consistent matching."""
        if self.os:
            self.normalized_os = normalize_os(self.os, default=self.os.lower())
        # Geo rules store uppercase ISO codes — normalize here so every rule
        # evaluation matches regardless of how the caller cased the input.
        if self.country_code:
            self.country_code = self.country_code.strip().upper()


@dataclass
class TargetingRule:
    """
    Represents a single targeting rule with priority and destination.
    """
    priority: int  # Higher = more specific
    destination_url: str
    rule_type: str  # "offer", "geo", "device", "campaign_default", "fallback"
    source_id: Optional[str] = None  # ID of the rule/offer/campaign
    matched_criteria: Optional[List[str]] = None  # What criteria matched
    
    def __lt__(self, other):
        """For sorting by priority (descending)."""
        return self.priority > other.priority


class TargetingEngine:
    """
    Centralized targeting engine.
    Resolves click destinations with deterministic priority.
    """
    
    def __init__(self, db, redis=None):
        self.db = db
        self.redis = redis
    
    async def resolve_destination(
        self,
        context: ClickContext,
        skip_prelander: bool = False
    ) -> Tuple[str, bool, Dict]:
        """
        Main entry point for destination resolution.
        
        Args:
            context: Click context (publisher, website, geo, device, etc.)
            skip_prelander: If True, return offer URL directly (for direct redirect mode)
        
        Returns:
            (destination_url, referrer_suppression, metadata)
        """
        # Collect all matching rules
        rules = await self._collect_targeting_rules(context)
        
        if not rules:
            logger.warning(f"[TARGETING] No rules matched for context: {context}")
            return FALLBACK_URL, False, {"rule_type": "fallback", "matched": False}
        
        # Sort by priority (highest first) and select winner
        rules.sort()
        winner = rules[0]
        
        logger.info(
            f"[TARGETING] Resolved destination: {winner.destination_url} "
            f"(priority={winner.priority}, type={winner.rule_type}, "
            f"criteria={winner.matched_criteria})"
        )
        
        # Check referrer suppression from campaign
        referrer_suppression = False
        if context.campaign_id:
            from bson import ObjectId
            campaign = await self.db.campaigns.find_one({"_id": context.campaign_id})
            if not campaign:
                try:
                    campaign = await self.db.campaigns.find_one({"_id": ObjectId(context.campaign_id)})
                except Exception:
                    pass
            if campaign:
                referrer_suppression = bool(campaign.get("referrer_suppression", False))
        
        metadata = {
            "rule_type": winner.rule_type,
            "priority": winner.priority,
            "source_id": winner.source_id,
            "matched_criteria": winner.matched_criteria,
            "total_rules_evaluated": len(rules),
        }
        
        return winner.destination_url, referrer_suppression, metadata
    
    async def _collect_targeting_rules(self, context: ClickContext) -> List[TargetingRule]:
        """
        Collect all applicable targeting rules for the given context.
        Returns list of rules with priority scores.
        """
        rules = []
        
        # 1. Check for direct offer targeting (most specific)
        offer_rules = await self._evaluate_offer_rules(context)
        rules.extend(offer_rules)
        
        # 2. Check GEO rules
        if context.campaign_id and context.country_code:
            geo_rules = await self._evaluate_geo_rules(context)
            rules.extend(geo_rules)
        
        # 3. Check Device/OS rules
        if context.campaign_id and context.device_type:
            device_rules = await self._evaluate_device_rules(context)
            rules.extend(device_rules)
        
        # 4. Check campaign default
        if context.campaign_id:
            campaign_rule = await self._evaluate_campaign_default(context)
            if campaign_rule:
                rules.append(campaign_rule)
        
        # 5. Always add global fallback
        fallback_rule = await self._evaluate_global_fallback()
        if fallback_rule:
            rules.append(fallback_rule)
        
        return rules
    
    async def _evaluate_offer_rules(self, context: ClickContext) -> List[TargetingRule]:
        """
        Evaluate offers with targeting criteria.
        Priority calculation:
        - Base: 1000
        - +500 per matched criterion (publisher, website, geo, os)
        - More criteria = higher priority
        """
        rules = []
        
        # Build query for eligible offers
        query = {"status": "active"}
        if context.campaign_id:
            from app.utils.db_utils import campaign_id_filter
            cid_filter = campaign_id_filter(context.campaign_id)
            query["$or"] = [
                cid_filter,
                {"campaign_id": None},
                {"campaign_id": {"$exists": False}},
            ]
        
        offers = await self.db.offers.find(query).to_list(length=100)
        
        for offer in offers:
            matched_criteria = []
            priority = 1000  # Base priority for offers
            
            # Check OS targeting
            os_types = offer.get("os_types", [])
            if os_types:
                if not context.normalized_os or context.normalized_os not in [
                    t.lower() for t in os_types
                ]:
                    continue  # OS doesn't match, skip
                matched_criteria.append("os")
                priority += 500
            
            # Check country targeting
            country_codes = offer.get("country_codes", [])
            if country_codes:
                if not context.country_code or context.country_code.upper() not in [
                    c.upper() for c in country_codes
                ]:
                    continue  # Country doesn't match, skip
                matched_criteria.append("geo")
                priority += 500
            
            # Check publisher targeting
            from app.utils.db_utils import normalize_id
            pub_ids = offer.get("publisher_ids", [])
            if pub_ids:
                norm_pubs = {normalize_id(pid) for pid in pub_ids}
                if not context.publisher_id or normalize_id(context.publisher_id) not in norm_pubs:
                    continue  # Publisher doesn't match, skip
                matched_criteria.append("publisher")
                priority += 500
            
            # Check website targeting
            web_ids = offer.get("website_ids", [])
            if web_ids:
                norm_webs = {normalize_id(wid) for wid in web_ids}
                if not context.website_id or normalize_id(context.website_id) not in norm_webs:
                    continue  # Website doesn't match, skip
                matched_criteria.append("website")
                priority += 500
            
            # Offer matched!
            offer_url = offer.get("offer_url")
            if offer_url:
                rules.append(TargetingRule(
                    priority=priority,
                    destination_url=offer_url,
                    rule_type="offer",
                    source_id=str(offer.get("_id")),
                    matched_criteria=matched_criteria,
                ))
        
        return rules
    
    async def _evaluate_geo_rules(self, context: ClickContext) -> List[TargetingRule]:
        """
        Evaluate GEO-specific rules.
        Priority: 800 (less specific than multi-criteria offers)
        """
        rules = []
        
        # Geo rules store uppercase ISO codes (see campaign_router save logic);
        # normalize the visitor's code so a lower/mixed-case input still matches.
        geo_rule = await self.db.geo_rules.find_one(
            {
                "campaign_id": context.campaign_id,
                "country_code": (context.country_code or "").upper(),
            },
            sort=[("priority", -1)],
        )
        
        if geo_rule and geo_rule.get("offer_url"):
            rules.append(TargetingRule(
                priority=800,
                destination_url=geo_rule["offer_url"],
                rule_type="geo",
                source_id=str(geo_rule.get("_id")),
                matched_criteria=["geo"],
            ))
        
        return rules
    
    async def _evaluate_device_rules(self, context: ClickContext) -> List[TargetingRule]:
        """
        Evaluate Device/OS specific rules.
        Priority: 700 (base) + 100 if OS also matches
        """
        rules = []
        
        # Try OS-specific match first
        if context.normalized_os:
            rule = await self.db.device_rules.find_one(
                {
                    "campaign_id": context.campaign_id,
                    "device_type": context.device_type,
                    "os": context.normalized_os,
                },
                sort=[("priority", -1)],
            )
            
            if rule and rule.get("offer_url"):
                rules.append(TargetingRule(
                    priority=800,  # Device + OS
                    destination_url=rule["offer_url"],
                    rule_type="device",
                    source_id=str(rule.get("_id")),
                    matched_criteria=["device", "os"],
                ))
                return rules  # Most specific device rule found
        
        # Fall back to device_type only match
        rule = await self.db.device_rules.find_one(
            {
                "campaign_id": context.campaign_id,
                "device_type": context.device_type,
                "$or": [{"os": None}, {"os": {"$exists": False}}, {"os": ""}],
            },
            sort=[("priority", -1)],
        )
        
        if rule and rule.get("offer_url"):
            rules.append(TargetingRule(
                priority=700,  # Device only
                destination_url=rule["offer_url"],
                rule_type="device",
                source_id=str(rule.get("_id")),
                matched_criteria=["device"],
            ))
        
        return rules
    
    async def _evaluate_campaign_default(self, context: ClickContext) -> Optional[TargetingRule]:
        """
        Evaluate campaign default offer URL.
        Priority: 500 (lowest priority rule-based option)
        """
        from bson import ObjectId
        
        # Try both string and ObjectId formats
        campaign = await self.db.campaigns.find_one({"_id": context.campaign_id})
        if not campaign:
            try:
                campaign = await self.db.campaigns.find_one({"_id": ObjectId(context.campaign_id)})
            except Exception:
                pass
        
        if campaign and campaign.get("default_offer_url"):
            return TargetingRule(
                priority=500,
                destination_url=campaign["default_offer_url"],
                rule_type="campaign_default",
                source_id=str(campaign.get("_id")),
                matched_criteria=["campaign"],
            )
        
        return None
    
    async def _evaluate_global_fallback(self) -> Optional[TargetingRule]:
        """
        Evaluate global fallback URL from system settings.
        Priority: 0 (absolute last resort)
        """
        setting = await self.db.system_settings.find_one({"key": "global_default_offer_url"})
        
        fallback_url = setting.get("value") if setting else FALLBACK_URL
        
        return TargetingRule(
            priority=0,
            destination_url=fallback_url,
            rule_type="fallback",
            source_id=None,
            matched_criteria=[],
        )


async def resolve_campaign_for_click(click_data: dict, db) -> Optional[str]:
    """
    Resolve the appropriate campaign for a click.
    Checks (Domain Glossary "Campaign value" resolution order):
    1. Website-assigned campaign (registered publisher context)
    2. Specific OS + Country — active campaign for this OS that also has a
       geo rule for the visitor's country
    3. OS-specific campaign (device_os == visitor OS, no matching geo rule)
    4. Global campaign (device_os == "global")
    5. Weighted random from active global-capable campaigns
       (never serves an OS-specific campaign to the wrong OS)

    Returns: campaign_id (str) or None
    """
    website_id = click_data.get("website_id")
    os_name = click_data.get("os")
    country_code = click_data.get("country_code")
    device_type = click_data.get("device_type", "desktop")

    # 1. Website-assigned campaign
    if website_id:
        website = await db.websites.find_one({"_id": website_id})
        if not website:
            try:
                from bson import ObjectId
                website = await db.websites.find_one({"_id": ObjectId(website_id)})
            except Exception:
                pass

        if website and website.get("assigned_campaign_id"):
            campaign = await db.campaigns.find_one({
                "_id": website["assigned_campaign_id"],
                "status": "active",
            })
            if not campaign:
                try:
                    from bson import ObjectId
                    campaign = await db.campaigns.find_one({
                        "_id": ObjectId(website["assigned_campaign_id"]),
                        "status": "active",
                    })
                except Exception:
                    pass
            if campaign:
                return str(campaign["_id"])

    mapped_os = normalize_os(os_name) if os_name else None

    # 2. Specific OS + Country — campaign for this OS with a geo rule for
    # the visitor's country.
    if mapped_os and country_code:
        cc = country_code.upper()
        geo_rule = await db.geo_rules.find_one(
            {"country_code": cc, "status": {"$ne": "deleted"}},
            sort=[("priority", -1)],
        )
        if geo_rule and geo_rule.get("campaign_id"):
            campaign = await db.campaigns.find_one({
                "_id": _campaign_oid(geo_rule["campaign_id"]),
                "device_os": mapped_os,
                "status": "active",
            })
            if not campaign:
                try:
                    from bson import ObjectId
                    campaign = await db.campaigns.find_one({
                        "_id": ObjectId(geo_rule["campaign_id"]),
                        "device_os": mapped_os,
                        "status": "active",
                    })
                except Exception:
                    pass
            if campaign:
                return str(campaign["_id"])

    # 3. OS-specific campaign
    if mapped_os:
        campaign = await db.campaigns.find_one({
            "device_os": mapped_os,
            "status": "active",
        })
        if campaign:
            return str(campaign["_id"])

    # 4. Global campaign
    campaign = await db.campaigns.find_one({
        "device_os": "global",
        "status": "active",
    })
    if campaign:
        return str(campaign["_id"])

    # 5. Weighted random selection — restricted to global-capable campaigns so an
    # OS-specific campaign is never served to the wrong OS.
    campaigns = await db.campaigns.find({
        "status": "active",
        "$or": [
            {"device_os": "global"},
            {"device_os": None},
            {"device_os": {"$exists": False}},
        ],
    }).to_list(length=None)
    if campaigns:
        from app.services.campaign_service import select_weighted_campaign
        campaign = select_weighted_campaign(campaigns)
        if campaign:
            return str(campaign.get("_id", campaign.get("id", "")))

    return None


def _campaign_oid(value):
    """Coerce a campaign reference to ObjectId when possible, else pass through."""
    try:
        from bson import ObjectId
        if isinstance(value, str) and ObjectId.is_valid(value):
            return ObjectId(value)
    except Exception:
        pass
    return value
