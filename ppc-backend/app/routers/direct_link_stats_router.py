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

async def _ensure_direct_link_stats_available(publisher_id: str, db) -> None:
    """
    Publisher status rule: banned/removed (or deleted) publishers lose Direct
    Link Stats while their traffic keeps redirecting. Raise 403 so the admin UI
    can show "unavailable" rather than a missing-publisher 404.
    """
    from app.services.publisher_service import is_publisher_banned_or_removed

    if await is_publisher_banned_or_removed(publisher_id, db):
        raise HTTPException(
            status_code=403,
            detail="Direct Link Stats unavailable: publisher is banned or removed",
        )


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
    await _ensure_direct_link_stats_available(publisher_id, db)

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

    # Publisher status rule: banned/removed publishers lose Direct Link Stats.
    if link.get("publisher_id"):
        await _ensure_direct_link_stats_available(link["publisher_id"], db)

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
    # Publisher status rule: banned/removed publishers lose Direct Link Stats.
    if publisher_id:
        await _ensure_direct_link_stats_available(publisher_id, db)

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

    # Publisher status rule: banned/removed publishers lose Direct Link Stats.
    await _ensure_direct_link_stats_available(data.publisher_id, db)

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
    update_fields = {
        "conversions": data.conversions,
        "updated_at": now,
    }
    # Reason is optional on conversion entries: only overwrite it when the
    # caller actually supplied one, so an edit that omits the field keeps
    # the previously stored value instead of wiping it to None.
    if data.reason is not None:
        update_fields["reason"] = data.reason
    await db.direct_link_manual_conversions.update_one(
        {"_id": oid},
        {"$set": update_fields},
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



# ─── Publisher Domain Stats ───────────────────────────────────────────────────

@router.get("/publisher-domains")
async def get_publisher_domains(
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Get all publishers with their assigned domains and real traffic stats.

    Each row carries:
    - domains: the Anchor/Inter/Prelander domains ASSIGNED to the publisher
      (publisher_ids membership)
    - defaults: the GLOBAL default domain per type (is_default flag) — the
      domains the publisher falls back to when nothing is explicitly assigned
    - clicks: REAL traffic numbers from the clicks collection (smartlink
      traffic), plus today's conversions (tracked events + admin-entered
      manual conversions). The link document's own counters only ever track
      masked-page hits, so the Direct Link Stats table showed zeros for every
      publisher whose traffic is smartlink-based.
    """
    from app.core.glossary import normalize_domain_type
    from app.core.constants import DOMAIN_TYPE_ANCHOR, DOMAIN_TYPE_INTER, DOMAIN_TYPE_PRELANDER

    # Get all redirection domains
    domains_cursor = db.redirection_domains.find({"status": "active"})
    domains = await domains_cursor.to_list(length=1000)
    
    # Debug: log how many domains have publisher_ids
    domains_with_pubs = [d for d in domains if d.get("publisher_ids")]
    logger.info(
        f"[DirectLinkStats] Total active domains: {len(domains)}, "
        f"with publisher_ids: {len(domains_with_pubs)}"
    )
    if domains_with_pubs:
        sample = domains_with_pubs[0]
        logger.info(
            f"[DirectLinkStats] Sample domain: {sample.get('domain')} "
            f"type={sample.get('domain_type')} "
            f"publisher_ids={sample.get('publisher_ids')}"
        )

    # Get all publishers
    publishers_cursor = db.publishers.find({"role": "publisher"})
    publishers = await publishers_cursor.to_list(length=500)

    # Build publisher -> domains mapping
    publisher_domains = {}

    # Global default domain per type (is_default on an active domain).
    defaults: Dict[str, str] = {}
    for domain in domains:
        if not domain.get("is_default"):
            continue
        dtype = normalize_domain_type(domain.get("domain_type"), default="unknown")
        if dtype in (DOMAIN_TYPE_ANCHOR, DOMAIN_TYPE_INTER, DOMAIN_TYPE_PRELANDER):
            defaults.setdefault(dtype, domain.get("domain", ""))

    for domain in domains:
        domain_type = normalize_domain_type(domain.get("domain_type"), default="unknown")
        publisher_ids = domain.get("publisher_ids", [])
        domain_name = domain.get("domain")
        
        # Debug: log each domain with publishers
        if publisher_ids:
            logger.info(
                f"[DirectLinkStats] Processing domain {domain_name} ({domain_type}) "
                f"with publisher_ids: {[str(pid) for pid in publisher_ids]}"
            )

        for pub_id in publisher_ids:
            # Normalize publisher_id to string for consistent comparison
            # (publisher_ids field might contain ObjectId or string)
            pub_id_str = str(pub_id)
            
            if pub_id_str not in publisher_domains:
                publisher_domains[pub_id_str] = {
                    "anchor": [],
                    "inter": [],
                    "prelander": [],
                }

            if domain_type == DOMAIN_TYPE_ANCHOR:
                publisher_domains[pub_id_str]["anchor"].append(domain_name)
                logger.info(f"[DirectLinkStats] Assigned anchor {domain_name} to publisher {pub_id_str}")
            elif domain_type == DOMAIN_TYPE_INTER:
                publisher_domains[pub_id_str]["inter"].append(domain_name)
                logger.info(f"[DirectLinkStats] Assigned inter {domain_name} to publisher {pub_id_str}")
            elif domain_type == DOMAIN_TYPE_PRELANDER:
                publisher_domains[pub_id_str]["prelander"].append(domain_name)
                logger.info(f"[DirectLinkStats] Assigned prelander {domain_name} to publisher {pub_id_str}")
    
    # Log summary of assignments
    logger.info(f"[DirectLinkStats] Total publishers with assigned domains: {len(publisher_domains)}")
    if publisher_domains:
        sample_pub_id = list(publisher_domains.keys())[0]
        logger.info(f"[DirectLinkStats] Sample assignment - Publisher {sample_pub_id}: {publisher_domains[sample_pub_id]}")

    # ── Real traffic stats per publisher (one aggregation per metric) ──────
    # clicks: the publisher's smartlink traffic (clicks collection, timestamp).
    click_pipeline = [
        {"$group": {"_id": "$publisher_id", "total": {"$sum": 1}}},
    ]
    click_rows = await db.clicks.aggregate(click_pipeline).to_list(length=None)
    total_clicks_map = {str(r["_id"]): r.get("total", 0) for r in click_rows}

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_click_rows = await db.clicks.aggregate([
        {"$match": {"timestamp": {"$gte": today_start}}},
        {"$group": {"_id": "$publisher_id", "total": {"$sum": 1}}},
    ]).to_list(length=None)
    today_clicks_map = {str(r["_id"]): r.get("total", 0) for r in today_click_rows}

    # Today's conversions — tracked direct-link events…
    today_conv_rows = await db.direct_link_events.aggregate([
        {"$match": {"created_at": {"$gte": today_start}}},
        {"$group": {"_id": "$publisher_id", "total": {"$sum": 1}}},
    ]).to_list(length=None)
    today_conv_map = {str(r["_id"]): r.get("total", 0) for r in today_conv_rows}

    # …plus admin-entered manual conversions dated today (both sources must
    # count — an entry entered this morning for today is one of them).
    today_str = today_start.strftime("%Y-%m-%d")
    manual_rows = await db.direct_link_manual_conversions.aggregate([
        {"$match": {"date": today_str}},
        {"$group": {"_id": "$publisher_id", "total": {"$sum": "$conversions"}}},
    ]).to_list(length=None)
    for r in manual_rows:
        pid = str(r["_id"])
        today_conv_map[pid] = today_conv_map.get(pid, 0) + (r.get("total", 0) or 0)

    # Build response
    results = []
    for pub in publishers:
        pub_id = str(pub["_id"])
        domains_info = publisher_domains.get(pub_id, {
            "anchor": [],
            "inter": [],
            "prelander": [],
        })

        # Debug logging for first 2 publishers
        if len(results) < 2:
            logger.info(
                f"[DirectLinkStats] Publisher {pub.get('name')} ({pub_id}): "
                f"anchor={domains_info.get('anchor', [])}, "
                f"inter={domains_info.get('inter', [])}, "
                f"prelander={domains_info.get('prelander', [])}"
            )

        results.append({
            "publisher_id": pub_id,
            "publisher_name": pub.get("name"),
            "publisher_email": pub.get("email"),
            "domains": {
                "anchor": domains_info.get("anchor", []),
                "inter": domains_info.get("inter", []),
                "prelander": domains_info.get("prelander", []),
                "total": len(domains_info.get("anchor", [])) + len(domains_info.get("inter", [])) + len(domains_info.get("prelander", [])),
            },
            # Global default domains (used when nothing is explicitly assigned)
            "defaults": {
                "anchor": defaults.get(DOMAIN_TYPE_ANCHOR, ""),
                "inter": defaults.get(DOMAIN_TYPE_INTER, ""),
                "prelander": defaults.get(DOMAIN_TYPE_PRELANDER, ""),
            },
            # Real traffic stats for the table's Clicks / Today columns.
            "clicks": {
                "total": total_clicks_map.get(pub_id, 0),
                "today": today_clicks_map.get(pub_id, 0),
                "today_conversions": today_conv_map.get(pub_id, 0),
            },
        })

    return {
        "success": True,
        "publisher_domains": results,
        "total_publishers": len(results),
    }
