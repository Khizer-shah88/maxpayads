from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from app.cache.campaign_cache import get_cached_campaigns, set_cached_campaigns, invalidate_campaign_cache
import logging

logger = logging.getLogger(__name__)


async def get_all_campaigns(db, redis=None, include_rules: bool = True) -> List[dict]:
    """Get all active campaigns with their geo and device rules."""
    if redis:
        cached = await get_cached_campaigns(redis)
        if cached:
            return cached

    cursor = db.campaigns.find({"status": {"$ne": "deleted"}})
    campaigns = await cursor.to_list(length=None)

    for campaign in campaigns:
        campaign["id"] = str(campaign.pop("_id", ""))
        if include_rules:
            geo_rules = await db.geo_rules.find(
                {"campaign_id": campaign["id"]}
            ).to_list(length=None)
            device_rules = await db.device_rules.find(
                {"campaign_id": campaign["id"]}
            ).to_list(length=None)
            for r in geo_rules:
                r["id"] = str(r.pop("_id", ""))
            for r in device_rules:
                r["id"] = str(r.pop("_id", ""))
            campaign["geo_rules"] = geo_rules
            campaign["device_rules"] = device_rules

    if redis:
        await set_cached_campaigns(redis, campaigns)

    return campaigns


def _campaign_id_filter(campaign_id: str) -> dict:
    """Build a filter that matches both ObjectId and string _id."""
    try:
        return {"_id": ObjectId(campaign_id)}
    except Exception:
        return {"_id": campaign_id}


async def get_campaign_by_id(campaign_id: str, db, include_rules: bool = True) -> Optional[dict]:
    campaign = await db.campaigns.find_one(_campaign_id_filter(campaign_id))
    if not campaign:
        return None
    campaign["id"] = str(campaign.pop("_id", ""))
    if include_rules:
        geo_rules = await db.geo_rules.find({"campaign_id": campaign["id"]}).to_list(length=None)
        device_rules = await db.device_rules.find({"campaign_id": campaign["id"]}).to_list(length=None)
        for r in geo_rules:
            r["id"] = str(r.pop("_id", ""))
        for r in device_rules:
            r["id"] = str(r.pop("_id", ""))
        campaign["geo_rules"] = geo_rules
        campaign["device_rules"] = device_rules
    return campaign


async def create_campaign(data: dict, db, redis=None) -> str:
    data.setdefault("status", "active")
    data["created_at"] = datetime.utcnow()
    data["updated_at"] = datetime.utcnow()
    result = await db.campaigns.insert_one(data)
    if redis:
        await invalidate_campaign_cache(redis)
    return str(result.inserted_id)


async def update_campaign(campaign_id: str, data: dict, db, redis=None) -> bool:
    data["updated_at"] = datetime.utcnow()
    result = await db.campaigns.update_one(
        _campaign_id_filter(campaign_id), {"$set": data}
    )
    if redis:
        await invalidate_campaign_cache(redis)
    return result.modified_count > 0


async def delete_campaign(campaign_id: str, db, redis=None) -> bool:
    result = await db.campaigns.update_one(
        _campaign_id_filter(campaign_id), {"$set": {"status": "deleted", "updated_at": datetime.utcnow()}}
    )
    if redis:
        await invalidate_campaign_cache(redis)
    return result.modified_count > 0


async def add_geo_rule(campaign_id: str, rule_data: dict, db, redis=None) -> str:
    rule_data["campaign_id"] = campaign_id
    rule_data["created_at"] = datetime.utcnow()
    result = await db.geo_rules.insert_one(rule_data)
    if redis:
        await invalidate_campaign_cache(redis)
    return str(result.inserted_id)


async def delete_geo_rule(rule_id: str, db, redis=None) -> bool:
    result = await db.geo_rules.delete_one(_campaign_id_filter(rule_id))
    if redis:
        await invalidate_campaign_cache(redis)
    return result.deleted_count > 0


async def add_device_rule(campaign_id: str, rule_data: dict, db, redis=None) -> str:
    rule_data["campaign_id"] = campaign_id
    rule_data["created_at"] = datetime.utcnow()
    result = await db.device_rules.insert_one(rule_data)
    if redis:
        await invalidate_campaign_cache(redis)
    return str(result.inserted_id)


async def delete_device_rule(rule_id: str, db, redis=None) -> bool:
    result = await db.device_rules.delete_one(_campaign_id_filter(rule_id))
    if redis:
        await invalidate_campaign_cache(redis)
    return result.deleted_count > 0


async def get_campaign_for_website(website_id: str, db) -> Optional[dict]:
    """Get campaign assigned to a website, or select from global campaigns."""
    website = await db.websites.find_one({"_id": website_id})
    if website and website.get("assigned_campaign_id"):
        return await get_campaign_by_id(website["assigned_campaign_id"], db)

    # Fall back to global campaign (weighted random selection)
    campaigns = await db.campaigns.find({"status": "active"}).to_list(length=None)
    if not campaigns:
        return None
    return select_weighted_campaign(campaigns)


def select_weighted_campaign(campaigns: List[dict]) -> Optional[dict]:
    """Select a campaign using weighted random rotation."""
    import random
    total_weight = sum(c.get("rotation_weight", 100) for c in campaigns)
    if total_weight == 0:
        return campaigns[0] if campaigns else None

    rand = random.uniform(0, total_weight)
    cumulative = 0
    for campaign in campaigns:
        cumulative += campaign.get("rotation_weight", 100)
        if rand <= cumulative:
            campaign["id"] = str(campaign.get("_id", campaign.get("id", "")))
            return campaign
    return campaigns[-1]
