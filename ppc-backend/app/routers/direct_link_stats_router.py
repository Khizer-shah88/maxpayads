"""
Direct Link Stats - Enhanced Statistics & Preferences Router

Provides:
- Stats profile preferences (show/hide metrics)
- Validated click tracking (unique, valid, invalid)
- OS/Country/Device breakdowns
- Manual conversion entries with history
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, Query, HTTPException

from app.dependencies import get_db, get_current_admin
from app.core.exceptions import NotFoundError
from app.schemas.stats_profile_schema import (
    StatsProfileCreate,
    StatsProfileUpdate,
    StatsProfileResponse,
    StatsProfilePreferences,
    ManualConversionCreate,
    ManualConversionUpdate,
    ManualConversionResponse,
)

router = APIRouter(prefix="/direct-links", tags=["Direct Link Stats"])
logger = logging.getLogger(__name__)


# ─── Stats Profile Endpoints ──────────────────────────────────────────────────

@router.post("/stats-profiles", status_code=201)
async def create_stats_profile(
    data: StatsProfileCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Create or update stats profile preferences for a publisher.
    Defines what metrics are visible in their stats dashboard.
    """
    try:
        pub_oid = ObjectId(data.publisher_id)
        publisher = await db.publishers.find_one({"_id": pub_oid})
        if not publisher:
            raise HTTPException(status_code=404, detail="Publisher not found")
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid publisher ID")
    
    # Check if profile already exists
    existing = await db.stats_profiles.find_one({"publisher_id": data.publisher_id})
    
    now = datetime.utcnow()
    
    if existing:
        # Update existing profile
        await db.stats_profiles.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "preferences": data.preferences.model_dump(),
                "updated_at": now,
            }}
        )
        doc = await db.stats_profiles.find_one({"_id": existing["_id"]})
        action = "updated"
    else:
        # Create new profile
        doc = {
            "publisher_id": data.publisher_id,
            "preferences": data.preferences.model_dump(),
            "created_at": now,
            "updated_at": now,
        }
        result = await db.stats_profiles.insert_one(doc)
        doc["_id"] = result.inserted_id
        action = "created"
    
    return {
        "success": True,
        "message": f"Stats profile {action}",
        "profile": {
            "id": str(doc["_id"]),
            "publisher_id": doc["publisher_id"],
            "preferences": doc["preferences"],
            "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
            "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else None,
        }
    }


@router.get("/stats-profiles/{publisher_id}")
async def get_stats_profile(
    publisher_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get stats profile preferences for a publisher."""
    profile = await db.stats_profiles.find_one({"publisher_id": publisher_id})
    
    if not profile:
        # Return default preferences if no profile exists
        return {
            "success": True,
            "profile": {
                "id": None,
                "publisher_id": publisher_id,
                "preferences": StatsProfilePreferences().model_dump(),
                "created_at": None,
                "updated_at": None,
            }
        }
    
    return {
        "success": True,
        "profile": {
            "id": str(profile["_id"]),
            "publisher_id": profile["publisher_id"],
            "preferences": profile.get("preferences", StatsProfilePreferences().model_dump()),
            "created_at": profile["created_at"].isoformat() if profile.get("created_at") else None,
            "updated_at": profile["updated_at"].isoformat() if profile.get("updated_at") else None,
        }
    }


@router.put("/stats-profiles/{publisher_id}")
async def update_stats_profile(
    publisher_id: str,
    data: StatsProfileUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Update stats profile preferences."""
    profile = await db.stats_profiles.find_one({"publisher_id": publisher_id})
    
    if not profile:
        raise HTTPException(status_code=404, detail="Stats profile not found")
    
    now = datetime.utcnow()
    await db.stats_profiles.update_one(
        {"_id": profile["_id"]},
        {"$set": {
            "preferences": data.preferences.model_dump(),
            "updated_at": now,
        }}
    )
    
    updated = await db.stats_profiles.find_one({"_id": profile["_id"]})
    
    return {
        "success": True,
        "message": "Stats profile updated",
        "profile": {
            "id": str(updated["_id"]),
            "publisher_id": updated["publisher_id"],
            "preferences": updated["preferences"],
            "updated_at": updated["updated_at"].isoformat(),
        }
    }


# ─── Stats Aggregation Endpoints ──────────────────────────────────────────────

@router.get("/stats/publisher/{publisher_id}")
async def get_publisher_stats(
    publisher_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Get aggregated stats for a publisher's direct links.
    Returns unique clicks, valid clicks, invalid clicks, OS breakdown, etc.
    """
    # Date range
    from app.utils.date_utils import timestamp_range_query
    date_range = timestamp_range_query(date_from, date_to) or {}
    
    # Query for events
    query = {"publisher_id": publisher_id}
    if date_range:
        query["created_at"] = date_range
    
    # Get all events
    events = await db.direct_link_events.find(query).to_list(length=10000)
    
    # Calculate metrics
    total_clicks = len(events)
    unique_clicks = len(set(e.get("ip_address") for e in events if e.get("ip_address")))
    valid_clicks = sum(1 for e in events if e.get("is_valid", True))
    invalid_clicks = sum(1 for e in events if not e.get("is_valid", True))
    fraud_clicks = sum(1 for e in events if e.get("is_fraud", False))
    
    # OS breakdown
    os_counts: Dict[str, int] = {}
    for event in events:
        os_name = event.get("os", "Unknown")
        os_counts[os_name] = os_counts.get(os_name, 0) + 1
    
    # Country breakdown
    country_counts: Dict[str, int] = {}
    for event in events:
        country = event.get("country_code", "Unknown")
        country_counts[country] = country_counts.get(country, 0) + 1
    
    # Device breakdown
    device_counts: Dict[str, int] = {}
    for event in events:
        device = event.get("device_type", "Unknown")
        device_counts[device] = device_counts.get(device, 0) + 1
    
    # Get manual conversions for date range
    manual_conv_query = {"publisher_id": publisher_id}
    if date_from:
        manual_conv_query.setdefault("date", {})["$gte"] = date_from
    if date_to:
        manual_conv_query.setdefault("date", {})["$lte"] = date_to
    
    manual_conversions = await db.direct_link_manual_conversions.find(manual_conv_query).to_list(length=1000)
    total_manual_conversions = sum(mc.get("conversions", 0) for mc in manual_conversions)
    
    # Calculate conversion rate
    conversions = total_clicks + total_manual_conversions  # Using clicks as conversions for now
    cr = (conversions / valid_clicks * 100) if valid_clicks > 0 else 0
    
    # Average fraud score
    fraud_scores = [e.get("fraud_score", 0) for e in events if e.get("fraud_score") is not None]
    avg_fraud_score = sum(fraud_scores) / len(fraud_scores) if fraud_scores else 0
    
    return {
        "success": True,
        "publisher_id": publisher_id,
        "date_from": date_from,
        "date_to": date_to,
        "stats": {
            "total_clicks": total_clicks,
            "unique_clicks": unique_clicks,
            "valid_clicks": valid_clicks,
            "invalid_clicks": invalid_clicks,
            "fraud_clicks": fraud_clicks,
            "conversions": conversions,
            "manual_conversions": total_manual_conversions,
            "conversion_rate": round(cr, 2),
            "avg_fraud_score": round(avg_fraud_score, 3),
        },
        "os_breakdown": dict(sorted(os_counts.items(), key=lambda x: x[1], reverse=True)),
        "country_breakdown": dict(sorted(country_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
        "device_breakdown": dict(sorted(device_counts.items(), key=lambda x: x[1], reverse=True)),
    }


@router.get("/stats/link/{link_id}")
async def get_link_stats(
    link_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get detailed stats for a specific direct link."""
    # Verify link exists
    try:
        link = await db.direct_links.find_one({"_id": ObjectId(link_id)})
        if not link:
            raise HTTPException(status_code=404, detail="Link not found")
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid link ID")
    
    # Date range
    from app.utils.date_utils import timestamp_range_query
    date_range = timestamp_range_query(date_from, date_to) or {}
    
    # Query for events
    query = {"link_id": link_id}
    if date_range:
        query["created_at"] = date_range
    
    # Get all events
    events = await db.direct_link_events.find(query).to_list(length=10000)
    
    # Calculate metrics (same as publisher stats)
    total_clicks = len(events)
    unique_clicks = len(set(e.get("ip_address") for e in events if e.get("ip_address")))
    valid_clicks = sum(1 for e in events if e.get("is_valid", True))
    invalid_clicks = sum(1 for e in events if not e.get("is_valid", True))
    
    # OS breakdown
    os_counts: Dict[str, int] = {}
    for event in events:
        os_name = event.get("os", "Unknown")
        os_counts[os_name] = os_counts.get(os_name, 0) + 1
    
    return {
        "success": True,
        "link_id": link_id,
        "link_name": link.get("name"),
        "stats": {
            "total_clicks": total_clicks,
            "unique_clicks": unique_clicks,
            "valid_clicks": valid_clicks,
            "invalid_clicks": invalid_clicks,
        },
        "os_breakdown": dict(sorted(os_counts.items(), key=lambda x: x[1], reverse=True)),
    }


@router.get("/stats/os-breakdown")
async def get_os_breakdown(
    publisher_id: Optional[str] = Query(None),
    link_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get OS breakdown statistics."""
    from app.utils.date_utils import timestamp_range_query
    date_range = timestamp_range_query(date_from, date_to) or {}
    
    query: Dict = {}
    if publisher_id:
        query["publisher_id"] = publisher_id
    if link_id:
        query["link_id"] = link_id
    if date_range:
        query["created_at"] = date_range
    
    # Aggregate by OS
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$os",
            "total_clicks": {"$sum": 1},
            "valid_clicks": {"$sum": {"$cond": [{"$eq": ["$is_valid", True]}, 1, 0]}},
            "unique_ips": {"$addToSet": "$ip_address"},
        }},
        {"$project": {
            "os": "$_id",
            "total_clicks": 1,
            "valid_clicks": 1,
            "unique_clicks": {"$size": "$unique_ips"},
        }},
        {"$sort": {"total_clicks": -1}},
    ]
    
    results = await db.direct_link_events.aggregate(pipeline).to_list(length=None)
    
    os_stats = []
    for r in results:
        os_stats.append({
            "os": r.get("os") or "Unknown",
            "total_clicks": r.get("total_clicks", 0),
            "valid_clicks": r.get("valid_clicks", 0),
            "unique_clicks": r.get("unique_clicks", 0),
        })
    
    return {
        "success": True,
        "os_breakdown": os_stats,
    }


# ─── Manual Conversion Endpoints ──────────────────────────────────────────────

@router.post("/manual-conversions", status_code=201)
async def create_manual_conversion(
    data: ManualConversionCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Add manual conversion entry for a specific date.
    Allows admin to manually record conversions that occurred outside the tracking system.
    """
    # Validate publisher exists
    try:
        pub_oid = ObjectId(data.publisher_id)
        publisher = await db.publishers.find_one({"_id": pub_oid})
        if not publisher:
            raise HTTPException(status_code=404, detail="Publisher not found")
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid publisher ID")
    
    # Validate link if provided
    link_name = None
    if data.link_id:
        try:
            link = await db.direct_links.find_one({"_id": ObjectId(data.link_id)})
            if not link:
                raise HTTPException(status_code=404, detail="Link not found")
            link_name = link.get("name")
        except InvalidId:
            raise HTTPException(status_code=400, detail="Invalid link ID")
    
    # Check if entry already exists for this date/publisher/link
    existing_query = {
        "date": data.date,
        "publisher_id": data.publisher_id,
    }
    if data.link_id:
        existing_query["link_id"] = data.link_id
    else:
        existing_query["link_id"] = None
    
    existing = await db.direct_link_manual_conversions.find_one(existing_query)
    
    now = datetime.utcnow()
    
    if existing:
        # Update existing entry
        await db.direct_link_manual_conversions.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "conversions": data.conversions,
                "reason": data.reason,
                "updated_at": now,
            }}
        )
        doc = await db.direct_link_manual_conversions.find_one({"_id": existing["_id"]})
        action = "updated"
    else:
        # Create new entry
        doc = {
            "date": data.date,
            "publisher_id": data.publisher_id,
            "link_id": data.link_id,
            "conversions": data.conversions,
            "reason": data.reason,
            "entered_by": str(current_user["id"]),
            "created_at": now,
            "updated_at": now,
        }
        result = await db.direct_link_manual_conversions.insert_one(doc)
        doc["_id"] = result.inserted_id
        action = "created"
    
    return {
        "success": True,
        "message": f"Manual conversion {action}",
        "conversion": {
            "id": str(doc["_id"]),
            "date": doc["date"],
            "publisher_id": doc["publisher_id"],
            "publisher_name": publisher.get("name"),
            "link_id": doc.get("link_id"),
            "link_name": link_name,
            "conversions": doc["conversions"],
            "reason": doc["reason"],
            "entered_by": doc["entered_by"],
            "created_at": doc["created_at"].isoformat(),
        }
    }


@router.get("/manual-conversions")
async def list_manual_conversions(
    publisher_id: Optional[str] = Query(None),
    link_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get manual conversion history with optional filtering."""
    query: Dict = {}
    
    if publisher_id:
        query["publisher_id"] = publisher_id
    if link_id:
        query["link_id"] = link_id
    
    # Date range filter on 'date' field (YYYY-MM-DD string)
    if date_from or date_to:
        date_filter: Dict = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to
        query["date"] = date_filter
    
    cursor = db.direct_link_manual_conversions.find(query).sort("date", -1)
    docs = await cursor.to_list(length=1000)
    
    # Enrich with publisher/link names
    publisher_ids = list(set(d["publisher_id"] for d in docs))
    link_ids = list(set(d.get("link_id") for d in docs if d.get("link_id")))
    
    # Fetch publishers
    pub_map: Dict[str, str] = {}
    if publisher_ids:
        pubs = await db.publishers.find(
            {"_id": {"$in": [ObjectId(pid) for pid in publisher_ids if pid]}}
        ).to_list(length=None)
        pub_map = {str(p["_id"]): p.get("name", "Unknown") for p in pubs}
    
    # Fetch links
    link_map: Dict[str, str] = {}
    if link_ids:
        links = await db.direct_links.find(
            {"_id": {"$in": [ObjectId(lid) for lid in link_ids if lid]}}
        ).to_list(length=None)
        link_map = {str(l["_id"]): l.get("name", "Unknown") for l in links}
    
    # Build response
    conversions = []
    for doc in docs:
        conversions.append({
            "id": str(doc["_id"]),
            "date": doc["date"],
            "publisher_id": doc["publisher_id"],
            "publisher_name": pub_map.get(doc["publisher_id"], "Unknown"),
            "link_id": doc.get("link_id"),
            "link_name": link_map.get(doc.get("link_id"), "") if doc.get("link_id") else "All Links",
            "conversions": doc["conversions"],
            "reason": doc["reason"],
            "entered_by": doc.get("entered_by"),
            "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
            "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else None,
        })
    
    return {
        "success": True,
        "conversions": conversions,
        "total": len(conversions),
    }


@router.put("/manual-conversions/{conversion_id}")
async def update_manual_conversion(
    conversion_id: str,
    data: ManualConversionUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Update existing manual conversion entry."""
    try:
        oid = ObjectId(conversion_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid conversion ID")
    
    doc = await db.direct_link_manual_conversions.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Manual conversion not found")
    
    now = datetime.utcnow()
    await db.direct_link_manual_conversions.update_one(
        {"_id": oid},
        {"$set": {
            "conversions": data.conversions,
            "reason": data.reason,
            "updated_at": now,
        }}
    )
    
    updated = await db.direct_link_manual_conversions.find_one({"_id": oid})
    
    return {
        "success": True,
        "message": "Manual conversion updated",
        "conversion": {
            "id": str(updated["_id"]),
            "date": updated["date"],
            "conversions": updated["conversions"],
            "reason": updated["reason"],
            "updated_at": updated["updated_at"].isoformat(),
        }
    }


@router.delete("/manual-conversions/{conversion_id}")
async def delete_manual_conversion(
    conversion_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Delete a manual conversion entry."""
    try:
        oid = ObjectId(conversion_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid conversion ID")
    
    result = await db.direct_link_manual_conversions.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Manual conversion not found")
    
    return {
        "success": True,
        "message": "Manual conversion deleted"
    }
