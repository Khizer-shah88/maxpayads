"""
Direct Link Stats Profile Service
==================================

Business logic for stats profile management and statistics aggregation.

Security:
- Opaque slugs (no internal IDs exposed)
- No leakage of campaign/domain information
- Publisher/source association only
- Canonical click validation
"""

import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

# 8-character base62 slug for profiles
_SLUG_CHARS = string.ascii_letters + string.digits


def generate_profile_slug(length: int = 8) -> str:
    """Generate cryptographically random opaque slug."""
    return "".join(secrets.choice(_SLUG_CHARS) for _ in range(length))


async def ensure_unique_slug(db) -> str:
    """Generate unique profile slug with collision detection."""
    for _ in range(20):
        slug = generate_profile_slug()
        existing = await db.stats_profiles.find_one({"slug": slug})
        if not existing:
            return slug
    raise RuntimeError("Could not generate unique slug after 20 attempts")


def build_stats_url(slug: str, stats_domain: Optional[str] = None) -> str:
    """Build public stats URL for a profile."""
    domain = stats_domain or "stats.example.com"  # Default from config
    return f"https://{domain}/s/{slug}"


async def get_publisher_name(db, publisher_id: str) -> Optional[str]:
    """Get publisher name for display."""
    try:
        obj_id = ObjectId(publisher_id)
    except Exception:
        return None
    
    publisher = await db.publishers.find_one({"_id": obj_id}, {"name": 1, "email": 1})
    if publisher:
        return publisher.get("name") or publisher.get("email")
    return None


def serialize_profile(doc: dict, publisher_name: Optional[str] = None) -> dict:
    """Serialize profile document to API response."""
    # Default preferences if not set
    default_preferences = {
        "show_os": True,
        "show_country": True,
        "show_device": True,
        "show_clicks": True,
        "show_unique_clicks": True,
        "show_valid_clicks": True,
        "show_invalid_clicks": False,
        "show_impressions": True,
        "show_conversions": True,
        "show_cr": True,
        "show_fraud_score": False,
        "show_daily_breakdown": True,
    }
    
    return {
        "id": str(doc["_id"]),
        "slug": doc.get("slug", ""),
        "name": doc.get("name", ""),
        "publisher_id": doc.get("publisher_id", ""),
        "publisher_name": publisher_name,
        "source_name": doc.get("source_name"),
        "stats_domain": doc.get("stats_domain"),
        "stats_url": build_stats_url(doc.get("slug", ""), doc.get("stats_domain")),
        "status": doc.get("status", "active"),
        "notes": doc.get("notes"),
        "metadata": doc.get("metadata") or {},
        "preferences": doc.get("preferences") or default_preferences,
        # Statistics
        "total_impressions": doc.get("total_impressions", 0),
        "total_clicks": doc.get("total_clicks", 0),
        "unique_clicks": doc.get("unique_clicks", 0),
        "valid_clicks": doc.get("valid_clicks", 0),
        "invalid_clicks": doc.get("invalid_clicks", 0),
        "total_conversions": doc.get("total_conversions", 0),
        # Timestamps
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


async def aggregate_stats(
    db,
    profile_slug: str,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Aggregate statistics for a profile within date range.
    Uses canonical click data only - no redirect hops counted separately.
    """
    # Get profile
    profile = await db.stats_profiles.find_one({"slug": profile_slug})
    if not profile:
        return None
    
    profile_id = str(profile["_id"])
    
    # Build date filter
    date_filter = {"profile_id": profile_id}
    if date_from or date_to:
        date_filter["created_at"] = {}
        if date_from:
            date_filter["created_at"]["$gte"] = date_from
        if date_to:
            date_filter["created_at"]["$lte"] = date_to
    
    # Aggregate clicks (canonical only)
    click_stats = await db.stats_profile_clicks.aggregate([
        {"$match": date_filter},
        {"$group": {
            "_id": None,
            "total_clicks": {"$sum": 1},
            "unique_clicks": {"$addToSet": "$ip_address"},  # Unique by IP
            "valid_clicks": {
                "$sum": {"$cond": [{"$eq": ["$is_valid", True]}, 1, 0]}
            },
            "invalid_clicks": {
                "$sum": {"$cond": [{"$eq": ["$is_valid", False]}, 1, 0]}
            },
        }},
    ]).to_list(length=1)
    
    stats = {
        "total_clicks": 0,
        "unique_clicks": 0,
        "valid_clicks": 0,
        "invalid_clicks": 0,
    }
    
    if click_stats:
        s = click_stats[0]
        stats["total_clicks"] = s.get("total_clicks", 0)
        stats["unique_clicks"] = len(s.get("unique_clicks", []))
        stats["valid_clicks"] = s.get("valid_clicks", 0)
        stats["invalid_clicks"] = s.get("invalid_clicks", 0)
    
    # Aggregate impressions
    impression_count = await db.stats_profile_impressions.count_documents(date_filter)
    stats["impressions"] = impression_count
    
    # Aggregate conversions
    conversion_filter = date_filter.copy()
    conversion_count = await db.stats_profile_conversions.count_documents(conversion_filter)
    
    # Add manual conversions
    manual_filter = {"profile_slug": profile_slug}
    if date_from or date_to:
        manual_filter["date"] = {}
        if date_from:
            manual_filter["date"]["$gte"] = date_from.strftime("%Y-%m-%d")
        if date_to:
            manual_filter["date"]["$lte"] = date_to.strftime("%Y-%m-%d")
    
    manual_conversions = await db.stats_profile_manual_conversions.find(manual_filter).to_list(length=1000)
    manual_total = sum(mc.get("conversions", 0) for mc in manual_conversions)
    
    stats["conversions"] = conversion_count + manual_total
    stats["manual_conversions_data"] = [
        {
            "id": str(mc["_id"]),
            "date": mc.get("date"),
            "conversions": mc.get("conversions", 0),
            "reason": mc.get("reason", ""),
        }
        for mc in manual_conversions
    ]
    
    return stats


async def aggregate_os_stats(
    db,
    profile_slug: str,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Aggregate statistics by OS."""
    profile = await db.stats_profiles.find_one({"slug": profile_slug})
    if not profile:
        return []
    
    profile_id = str(profile["_id"])
    
    # Build filter
    match_filter = {"profile_id": profile_id}
    if date_from or date_to:
        match_filter["created_at"] = {}
        if date_from:
            match_filter["created_at"]["$gte"] = date_from
        if date_to:
            match_filter["created_at"]["$lte"] = date_to
    
    # Aggregate by OS
    pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": "$os",
            "clicks": {"$sum": 1},
            "valid_clicks": {
                "$sum": {"$cond": [{"$eq": ["$is_valid", True]}, 1, 0]}
            },
        }},
        {"$sort": {"clicks": -1}},
    ]
    
    os_stats = await db.stats_profile_clicks.aggregate(pipeline).to_list(length=100)
    
    return [
        {
            "os": stat["_id"] or "Unknown",
            "clicks": stat.get("clicks", 0),
            "valid_clicks": stat.get("valid_clicks", 0),
        }
        for stat in os_stats
    ]


async def aggregate_daily_stats(
    db,
    profile_slug: str,
    date_from: datetime,
    date_to: datetime,
) -> List[Dict[str, Any]]:
    """Aggregate statistics by day."""
    profile = await db.stats_profiles.find_one({"slug": profile_slug})
    if not profile:
        return []
    
    profile_id = str(profile["_id"])
    
    # Build filter
    match_filter = {
        "profile_id": profile_id,
        "created_at": {"$gte": date_from, "$lte": date_to},
    }
    
    # Aggregate by day
    pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": {
                "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
            },
            "clicks": {"$sum": 1},
            "valid_clicks": {
                "$sum": {"$cond": [{"$eq": ["$is_valid", True]}, 1, 0]}
            },
        }},
        {"$sort": {"_id": 1}},
    ]
    
    daily_clicks = await db.stats_profile_clicks.aggregate(pipeline).to_list(length=365)
    
    # Get daily impressions
    impression_pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": {
                "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
            },
            "impressions": {"$sum": 1},
        }},
    ]
    
    daily_impressions = await db.stats_profile_impressions.aggregate(impression_pipeline).to_list(length=365)
    impressions_map = {d["_id"]: d["impressions"] for d in daily_impressions}
    
    # Get daily conversions
    conversion_pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": {
                "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
            },
            "conversions": {"$sum": 1},
        }},
    ]
    
    daily_conversions = await db.stats_profile_conversions.aggregate(conversion_pipeline).to_list(length=365)
    conversions_map = {d["_id"]: d["conversions"] for d in daily_conversions}
    
    # Get manual conversions
    manual_conversions = await db.stats_profile_manual_conversions.find({
        "profile_slug": profile_slug,
        "date": {
            "$gte": date_from.strftime("%Y-%m-%d"),
            "$lte": date_to.strftime("%Y-%m-%d"),
        },
    }).to_list(length=365)
    manual_map = {mc["date"]: mc.get("conversions", 0) for mc in manual_conversions}
    
    # Combine all stats by day
    result = []
    for day_stat in daily_clicks:
        date = day_stat["_id"]
        result.append({
            "date": date,
            "impressions": impressions_map.get(date, 0),
            "clicks": day_stat.get("clicks", 0),
            "valid_clicks": day_stat.get("valid_clicks", 0),
            "conversions": conversions_map.get(date, 0) + manual_map.get(date, 0),
        })
    
    return result


async def track_impression(
    db,
    profile_slug: str,
    request_data: Dict[str, Any],
) -> bool:
    """Track an impression for a profile."""
    profile = await db.stats_profiles.find_one({"slug": profile_slug, "status": "active"})
    if not profile:
        return False
    
    impression = {
        "profile_id": str(profile["_id"]),
        "profile_slug": profile_slug,
        "ip_address": request_data.get("ip_address", ""),
        "user_agent": request_data.get("user_agent", "")[:500],
        "referrer": request_data.get("referrer", ""),
        "created_at": datetime.utcnow(),
    }
    
    await db.stats_profile_impressions.insert_one(impression)
    
    # Increment counter
    await db.stats_profiles.update_one(
        {"_id": profile["_id"]},
        {"$inc": {"total_impressions": 1}},
    )
    
    return True


async def track_click(
    db,
    profile_slug: str,
    click_data: Dict[str, Any],
) -> bool:
    """
    Track a canonical click for a profile.
    Only valid, deduplicated clicks are counted.
    """
    profile = await db.stats_profiles.find_one({"slug": profile_slug, "status": "active"})
    if not profile:
        return False
    
    # Validate click (simple validation - enhance as needed)
    is_valid = click_data.get("is_valid", True)
    
    click = {
        "profile_id": str(profile["_id"]),
        "profile_slug": profile_slug,
        "ip_address": click_data.get("ip_address", ""),
        "user_agent": click_data.get("user_agent", "")[:500],
        "referrer": click_data.get("referrer", ""),
        "os": click_data.get("os", ""),
        "device_type": click_data.get("device_type", ""),
        "country": click_data.get("country", ""),
        "is_valid": is_valid,
        "created_at": datetime.utcnow(),
    }
    
    await db.stats_profile_clicks.insert_one(click)
    
    # Increment counters
    update_inc = {"total_clicks": 1}
    if is_valid:
        update_inc["valid_clicks"] = 1
    else:
        update_inc["invalid_clicks"] = 1
    
    await db.stats_profiles.update_one(
        {"_id": profile["_id"]},
        {"$inc": update_inc},
    )
    
    return True


async def track_conversion(
    db,
    profile_slug: str,
    conversion_data: Dict[str, Any],
) -> bool:
    """Track a conversion for a profile."""
    profile = await db.stats_profiles.find_one({"slug": profile_slug, "status": "active"})
    if not profile:
        return False
    
    conversion = {
        "profile_id": str(profile["_id"]),
        "profile_slug": profile_slug,
        "ip_address": conversion_data.get("ip_address", ""),
        "metadata": conversion_data.get("metadata") or {},
        "created_at": datetime.utcnow(),
    }
    
    await db.stats_profile_conversions.insert_one(conversion)
    
    # Increment counter
    await db.stats_profiles.update_one(
        {"_id": profile["_id"]},
        {"$inc": {"total_conversions": 1}},
    )
    
    return True
