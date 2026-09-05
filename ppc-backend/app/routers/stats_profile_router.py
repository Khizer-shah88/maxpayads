"""
Direct Link Stats Profile Router
=================================

Admin endpoints for managing stats profiles and public endpoints
for viewing statistics with opaque slugs.

Security:
- Admin-only CRUD operations
- Public stats access via opaque slug only
- No internal IDs or campaign info exposed
- Canonical click validation
"""

from datetime import datetime, timedelta
from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, Query, HTTPException, Request

from app.dependencies import get_db, get_current_admin
from app.core.exceptions import NotFoundError
from app.schemas.direct_link_stats_profile_schema import (
    StatsProfileCreate,
    StatsProfileUpdate,
    ManualConversionCreate,
    ManualConversionUpdate,
)
from app.services import stats_profile_service as sps

router = APIRouter(prefix="/stats-profiles", tags=["Stats Profiles"])


# ─── Helper Functions ─────────────────────────────────────────────────────────

def _oid(profile_id: str) -> ObjectId:
    """Convert string ID to ObjectId."""
    try:
        return ObjectId(profile_id)
    except (InvalidId, TypeError):
        raise NotFoundError("Stats Profile")


def _parse_date(date_str: Optional[str], default: Optional[datetime] = None) -> Optional[datetime]:
    """Parse date string to datetime."""
    if not date_str:
        return default
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")


# ─── Admin Endpoints ──────────────────────────────────────────────────────────

@router.get("/admin")
async def list_profiles(
    publisher_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """List all stats profiles with filtering."""
    query = {}
    
    if publisher_id:
        query["publisher_id"] = publisher_id
    if status:
        query["status"] = status
    
    cursor = db.stats_profiles.find(query).sort("created_at", -1)
    profiles = await cursor.to_list(length=500)
    
    # Get publisher names
    publisher_ids = list(set(p.get("publisher_id") for p in profiles if p.get("publisher_id")))
    publisher_names = {}
    
    for pid in publisher_ids:
        name = await sps.get_publisher_name(db, pid)
        if name:
            publisher_names[pid] = name
    
    result = [
        sps.serialize_profile(p, publisher_names.get(p.get("publisher_id")))
        for p in profiles
    ]
    
    return {
        "success": True,
        "profiles": result,
        "total": len(result),
    }


@router.get("/admin/{profile_id}")
async def get_profile(
    profile_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get a single stats profile by ID."""
    profile = await db.stats_profiles.find_one({"_id": _oid(profile_id)})
    if not profile:
        raise NotFoundError("Stats Profile")
    
    publisher_name = await sps.get_publisher_name(db, profile.get("publisher_id", ""))
    
    return {
        "success": True,
        "profile": sps.serialize_profile(profile, publisher_name),
    }


@router.post("/admin", status_code=201)
async def create_profile(
    data: StatsProfileCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Create a new stats profile."""
    # Generate unique slug
    slug = await sps.ensure_unique_slug(db)
    
    now = datetime.utcnow()
    profile = {
        "slug": slug,
        "name": data.name,
        "publisher_id": data.publisher_id,
        "source_name": data.source_name,
        "stats_domain": data.stats_domain,
        "status": data.status,
        "notes": data.notes,
        "metadata": data.metadata,
        "preferences": data.preferences.model_dump() if data.preferences else {},
        # Initialize counters
        "total_impressions": 0,
        "total_clicks": 0,
        "unique_clicks": 0,
        "valid_clicks": 0,
        "invalid_clicks": 0,
        "total_conversions": 0,
        # Timestamps
        "created_at": now,
        "updated_at": now,
    }
    
    result = await db.stats_profiles.insert_one(profile)
    profile["_id"] = result.inserted_id
    
    publisher_name = await sps.get_publisher_name(db, data.publisher_id)
    
    return {
        "success": True,
        "profile": sps.serialize_profile(profile, publisher_name),
        "message": "Stats profile created",
    }


@router.put("/admin/{profile_id}")
async def update_profile(
    profile_id: str,
    data: StatsProfileUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Update an existing stats profile."""
    profile = await db.stats_profiles.find_one({"_id": _oid(profile_id)})
    if not profile:
        raise NotFoundError("Stats Profile")
    
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    
    await db.stats_profiles.update_one(
        {"_id": _oid(profile_id)},
        {"$set": update_data},
    )
    
    updated = await db.stats_profiles.find_one({"_id": _oid(profile_id)})
    publisher_name = await sps.get_publisher_name(db, updated.get("publisher_id", ""))
    
    return {
        "success": True,
        "profile": sps.serialize_profile(updated, publisher_name),
        "message": "Stats profile updated",
    }


@router.delete("/admin/{profile_id}")
async def delete_profile(
    profile_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Delete a stats profile and all associated data."""
    profile = await db.stats_profiles.find_one({"_id": _oid(profile_id)})
    if not profile:
        raise NotFoundError("Stats Profile")
    
    profile_id_str = str(profile["_id"])
    profile_slug = profile.get("slug", "")
    
    # Delete associated data
    await db.stats_profile_impressions.delete_many({"profile_id": profile_id_str})
    await db.stats_profile_clicks.delete_many({"profile_id": profile_id_str})
    await db.stats_profile_conversions.delete_many({"profile_id": profile_id_str})
    await db.stats_profile_manual_conversions.delete_many({"profile_slug": profile_slug})
    
    # Delete profile
    await db.stats_profiles.delete_one({"_id": _oid(profile_id)})
    
    return {
        "success": True,
        "message": "Stats profile and associated data deleted",
    }


@router.patch("/admin/{profile_id}/regenerate-slug")
async def regenerate_slug(
    profile_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Regenerate the opaque slug for a profile."""
    profile = await db.stats_profiles.find_one({"_id": _oid(profile_id)})
    if not profile:
        raise NotFoundError("Stats Profile")
    
    old_slug = profile.get("slug", "")
    new_slug = await sps.ensure_unique_slug(db)
    
    # Update profile
    await db.stats_profiles.update_one(
        {"_id": _oid(profile_id)},
        {"$set": {"slug": new_slug, "updated_at": datetime.utcnow()}},
    )
    
    # Update all associated data
    await db.stats_profile_impressions.update_many(
        {"profile_slug": old_slug},
        {"$set": {"profile_slug": new_slug}},
    )
    await db.stats_profile_clicks.update_many(
        {"profile_slug": old_slug},
        {"$set": {"profile_slug": new_slug}},
    )
    await db.stats_profile_conversions.update_many(
        {"profile_slug": old_slug},
        {"$set": {"profile_slug": new_slug}},
    )
    await db.stats_profile_manual_conversions.update_many(
        {"profile_slug": old_slug},
        {"$set": {"profile_slug": new_slug}},
    )
    
    updated = await db.stats_profiles.find_one({"_id": _oid(profile_id)})
    publisher_name = await sps.get_publisher_name(db, updated.get("publisher_id", ""))
    
    return {
        "success": True,
        "profile": sps.serialize_profile(updated, publisher_name),
        "message": "Slug regenerated",
        "old_slug": old_slug,
        "new_slug": new_slug,
    }


# ─── Manual Conversions ───────────────────────────────────────────────────────

@router.post("/admin/{profile_id}/manual-conversions", status_code=201)
async def create_manual_conversion(
    profile_id: str,
    data: ManualConversionCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Add or update manual conversion override for a specific date."""
    profile = await db.stats_profiles.find_one({"_id": _oid(profile_id)})
    if not profile:
        raise NotFoundError("Stats Profile")
    
    profile_slug = profile.get("slug", "")
    
    # Check if override already exists for this date
    existing = await db.stats_profile_manual_conversions.find_one({
        "profile_slug": profile_slug,
        "date": data.date,
    })
    
    now = datetime.utcnow()
    
    if existing:
        # Update existing
        await db.stats_profile_manual_conversions.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "conversions": data.conversions,
                "reason": data.reason,
                "metadata": data.metadata,
                "updated_at": now,
                "updated_by": str(current_user["_id"]),
            }},
        )
        result_id = existing["_id"]
        message = "Manual conversion updated"
    else:
        # Create new
        manual_conversion = {
            "profile_id": str(profile["_id"]),
            "profile_slug": profile_slug,
            "date": data.date,
            "conversions": data.conversions,
            "reason": data.reason,
            "metadata": data.metadata,
            "created_at": now,
            "updated_at": now,
            "created_by": str(current_user["_id"]),
        }
        result = await db.stats_profile_manual_conversions.insert_one(manual_conversion)
        result_id = result.inserted_id
        message = "Manual conversion created"
    
    conversion = await db.stats_profile_manual_conversions.find_one({"_id": result_id})
    
    return {
        "success": True,
        "conversion": {
            "id": str(conversion["_id"]),
            "date": conversion.get("date"),
            "conversions": conversion.get("conversions", 0),
            "reason": conversion.get("reason", ""),
            "metadata": conversion.get("metadata") or {},
        },
        "message": message,
    }


@router.get("/admin/{profile_id}/manual-conversions")
async def list_manual_conversions(
    profile_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """List manual conversion overrides for a profile."""
    profile = await db.stats_profiles.find_one({"_id": _oid(profile_id)})
    if not profile:
        raise NotFoundError("Stats Profile")
    
    profile_slug = profile.get("slug", "")
    
    query = {"profile_slug": profile_slug}
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    
    cursor = db.stats_profile_manual_conversions.find(query).sort("date", -1)
    conversions = await cursor.to_list(length=1000)
    
    result = [
        {
            "id": str(c["_id"]),
            "date": c.get("date"),
            "conversions": c.get("conversions", 0),
            "reason": c.get("reason", ""),
            "metadata": c.get("metadata") or {},
            "created_at": c.get("created_at").isoformat() if c.get("created_at") else None,
            "updated_at": c.get("updated_at").isoformat() if c.get("updated_at") else None,
        }
        for c in conversions
    ]
    
    return {
        "success": True,
        "conversions": result,
        "total": len(result),
    }


@router.put("/admin/manual-conversions/{conversion_id}")
async def update_manual_conversion(
    conversion_id: str,
    data: ManualConversionUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Update a manual conversion override."""
    try:
        conv_oid = ObjectId(conversion_id)
    except (InvalidId, TypeError):
        raise NotFoundError("Manual Conversion")
    
    conversion = await db.stats_profile_manual_conversions.find_one({"_id": conv_oid})
    if not conversion:
        raise NotFoundError("Manual Conversion")
    
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    update_data["updated_by"] = str(current_user["_id"])
    
    await db.stats_profile_manual_conversions.update_one(
        {"_id": conv_oid},
        {"$set": update_data},
    )
    
    updated = await db.stats_profile_manual_conversions.find_one({"_id": conv_oid})
    
    return {
        "success": True,
        "conversion": {
            "id": str(updated["_id"]),
            "date": updated.get("date"),
            "conversions": updated.get("conversions", 0),
            "reason": updated.get("reason", ""),
            "metadata": updated.get("metadata") or {},
        },
        "message": "Manual conversion updated",
    }


@router.delete("/admin/manual-conversions/{conversion_id}")
async def delete_manual_conversion(
    conversion_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Delete a manual conversion override."""
    try:
        conv_oid = ObjectId(conversion_id)
    except (InvalidId, TypeError):
        raise NotFoundError("Manual Conversion")
    
    result = await db.stats_profile_manual_conversions.delete_one({"_id": conv_oid})
    
    if result.deleted_count == 0:
        raise NotFoundError("Manual Conversion")
    
    return {
        "success": True,
        "message": "Manual conversion deleted",
    }


# ─── Public Stats Endpoints ───────────────────────────────────────────────────

@router.get("/public/{slug}/stats")
async def get_public_stats(
    slug: str,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db=Depends(get_db),
):
    """
    Get statistics for a profile by opaque slug.
    Public endpoint - no authentication required.
    
    Returns aggregated stats with no internal information exposed.
    """
    # Verify profile exists and is active
    profile = await db.stats_profiles.find_one({"slug": slug, "status": "active"})
    if not profile:
        raise HTTPException(status_code=404, detail="Stats profile not found")
    
    # Parse dates
    from_date = _parse_date(date_from, datetime.utcnow() - timedelta(days=30))
    to_date = _parse_date(date_to, datetime.utcnow())
    
    # Aggregate stats
    stats = await sps.aggregate_stats(db, slug, from_date, to_date)
    os_stats = await sps.aggregate_os_stats(db, slug, from_date, to_date)
    daily_stats = await sps.aggregate_daily_stats(db, slug, from_date, to_date)
    
    return {
        "success": True,
        "profile_slug": slug,
        "date_from": from_date.strftime("%Y-%m-%d"),
        "date_to": to_date.strftime("%Y-%m-%d"),
        "stats": {
            "impressions": stats.get("impressions", 0),
            "clicks": stats.get("total_clicks", 0),
            "unique_clicks": stats.get("unique_clicks", 0),
            "valid_clicks": stats.get("valid_clicks", 0),
            "invalid_clicks": stats.get("invalid_clicks", 0),
            "conversions": stats.get("conversions", 0),
        },
        "os_breakdown": os_stats,
        "daily_breakdown": daily_stats,
        "manual_conversions": stats.get("manual_conversions_data", []),
    }


@router.post("/public/{slug}/impression")
async def track_impression(
    slug: str,
    request: Request,
    db=Depends(get_db),
):
    """Track an impression for a profile (public endpoint)."""
    # Extract request data
    request_data = {
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", ""),
        "referrer": request.headers.get("referer", ""),
    }
    
    success = await sps.track_impression(db, slug, request_data)
    
    if not success:
        raise HTTPException(status_code=404, detail="Stats profile not found or inactive")
    
    return {"success": True, "message": "Impression tracked"}


@router.post("/public/{slug}/click")
async def track_click(
    slug: str,
    request: Request,
    data: dict,
    db=Depends(get_db),
):
    """
    Track a canonical click for a profile (public endpoint).
    Only canonical, validated clicks should be sent here.
    """
    # Extract click data
    click_data = {
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", ""),
        "referrer": request.headers.get("referer", ""),
        "os": data.get("os", ""),
        "device_type": data.get("device_type", ""),
        "country": data.get("country", ""),
        "is_valid": data.get("is_valid", True),
    }
    
    success = await sps.track_click(db, slug, click_data)
    
    if not success:
        raise HTTPException(status_code=404, detail="Stats profile not found or inactive")
    
    return {"success": True, "message": "Click tracked"}


@router.post("/public/{slug}/conversion")
async def track_conversion(
    slug: str,
    request: Request,
    data: dict,
    db=Depends(get_db),
):
    """Track a conversion for a profile (public endpoint)."""
    conversion_data = {
        "ip_address": request.client.host if request.client else "unknown",
        "metadata": data.get("metadata") or {},
    }
    
    success = await sps.track_conversion(db, slug, conversion_data)
    
    if not success:
        raise HTTPException(status_code=404, detail="Stats profile not found or inactive")
    
    return {"success": True, "message": "Conversion tracked"}
