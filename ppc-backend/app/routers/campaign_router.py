from fastapi import APIRouter, Depends, Query
from typing import Optional
from bson import ObjectId
from app.schemas.campaign_schema import CampaignCreate, CampaignUpdate, GeoRuleCreate, DeviceRuleCreate, AssignCampaignRequest, DeviceCampaignSave
from app.services.campaign_service import (
    get_all_campaigns, get_campaign_by_id, create_campaign,
    update_campaign, delete_campaign, add_geo_rule, delete_geo_rule,
    add_device_rule, delete_device_rule,
)
from app.dependencies import get_db, get_redis_client, get_current_admin
from app.core.exceptions import NotFoundError
from app.cache.campaign_cache import invalidate_campaign_cache
from datetime import datetime

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.get("")
async def list_campaigns(
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    campaigns = await get_all_campaigns(db, redis)
    if status:
        campaigns = [c for c in campaigns if c.get("status") == status]
    return {"success": True, "campaigns": campaigns, "total": len(campaigns)}


@router.post("", status_code=201)
async def create_new_campaign(
    data: CampaignCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    campaign_id = await create_campaign(data.model_dump(), db, redis)
    return {"success": True, "campaign_id": campaign_id, "message": "Campaign created"}


# ─── Device-centric campaign endpoints (must be before /{campaign_id}) ───

@router.get("/by-device")
async def get_device_campaigns(
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get all device-centric campaigns grouped by OS."""
    cursor = db.campaigns.find({"device_os": {"$ne": None}, "status": {"$ne": "deleted"}})
    campaigns = await cursor.to_list(length=None)

    result = {}
    for c in campaigns:
        c["id"] = str(c.pop("_id", ""))
        os_key = c.get("device_os", "")
        geo_rules = await db.geo_rules.find({"campaign_id": c["id"]}).to_list(length=None)
        countries = [r["country_code"] for r in geo_rules]
        country_rules = [
            {
                "country_code": r["country_code"],
                "offer_url": r.get("offer_url", ""),
                "password": r.get("password", ""),
            }
            for r in geo_rules
        ]
        result[os_key] = {
            "id": c["id"],
            "name": c.get("name", ""),
            "offer_url": c.get("default_offer_url", ""),
            "password": c.get("password", ""),
            "countries": countries,
            "country_rules": country_rules,
            "status": c.get("status", "active"),
            "direct_redirect_mode": c.get("direct_redirect_mode", False),
            "referrer_suppression": c.get("referrer_suppression", False),
        }

    return {"success": True, "device_campaigns": result}


@router.put("/by-device/{device_os}")
async def save_device_campaign(
    device_os: str,
    data: DeviceCampaignSave,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    """Create or update a campaign for a specific device OS."""
    device_os = device_os.lower()
    valid_devices = ["windows", "mac", "android", "global"]
    if device_os not in valid_devices:
        return {"success": False, "message": f"Invalid device. Must be one of: {valid_devices}"}

    existing = await db.campaigns.find_one({"device_os": device_os, "status": {"$ne": "deleted"}})

    now = datetime.utcnow()
    if existing:
        campaign_id = str(existing["_id"])
        await db.campaigns.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "default_offer_url": data.offer_url,
                "password": data.password,
                "direct_redirect_mode": data.direct_redirect_mode,
                "referrer_suppression": data.referrer_suppression,
                "updated_at": now,
            }}
        )
    else:
        campaign_name = f"{device_os.capitalize()} Campaign"
        result = await db.campaigns.insert_one({
            "name": campaign_name,
            "status": "active",
            "default_offer_url": data.offer_url,
            "password": data.password,
            "device_os": device_os,
            "direct_redirect_mode": data.direct_redirect_mode,
            "referrer_suppression": data.referrer_suppression,
            "rotation_weight": 100,
            "created_at": now,
            "updated_at": now,
        })
        campaign_id = str(result.inserted_id)

    # Sync geo rules — remove all existing and re-add selected countries
    await db.geo_rules.delete_many({"campaign_id": campaign_id})

    # Build a lookup from country_rules for per-country URL/password
    country_rule_map = {}
    if data.country_rules:
        for cr in data.country_rules:
            country_rule_map[cr.country_code.upper()] = {
                "offer_url": cr.offer_url,
                "password": cr.password,
            }

    # Use country_rules if provided, otherwise fall back to countries list with default URL
    all_country_codes = set()
    if data.country_rules:
        all_country_codes = {cr.country_code.upper() for cr in data.country_rules}
    if data.countries:
        all_country_codes.update(cc.upper() for cc in data.countries)

    if all_country_codes:
        geo_docs = []
        for cc in all_country_codes:
            rule_data = country_rule_map.get(cc, {})
            geo_docs.append({
                "campaign_id": campaign_id,
                "country_code": cc,
                "offer_url": rule_data.get("offer_url", data.offer_url),
                "password": rule_data.get("password", ""),
                "priority": 0,
                "created_at": now,
            })
        await db.geo_rules.insert_many(geo_docs)

    if redis:
        await invalidate_campaign_cache(redis)

    return {"success": True, "message": f"{device_os.capitalize()} campaign saved", "campaign_id": campaign_id}


@router.delete("/by-device/{device_os}")
async def delete_device_campaign(
    device_os: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    """Delete a device campaign."""
    existing = await db.campaigns.find_one({"device_os": device_os.lower(), "status": {"$ne": "deleted"}})
    if not existing:
        raise NotFoundError("Device campaign")
    campaign_id = str(existing["_id"])
    await db.campaigns.update_one({"_id": existing["_id"]}, {"$set": {"status": "deleted", "updated_at": datetime.utcnow()}})
    await db.geo_rules.delete_many({"campaign_id": campaign_id})
    if redis:
        await invalidate_campaign_cache(redis)
    return {"success": True, "message": f"{device_os.capitalize()} campaign deleted"}


# ─── Standard campaign CRUD endpoints ───

@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    campaign = await get_campaign_by_id(campaign_id, db)
    if not campaign:
        raise NotFoundError("Campaign")
    return {"success": True, "campaign": campaign}


@router.put("/{campaign_id}")
async def update_campaign_endpoint(
    campaign_id: str,
    data: CampaignUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    updated = await update_campaign(campaign_id, update_data, db, redis)
    if not updated:
        raise NotFoundError("Campaign")
    return {"success": True, "message": "Campaign updated"}


@router.delete("/{campaign_id}")
async def delete_campaign_endpoint(
    campaign_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    deleted = await delete_campaign(campaign_id, db, redis)
    if not deleted:
        raise NotFoundError("Campaign")
    return {"success": True, "message": "Campaign deleted"}


@router.post("/{campaign_id}/geo-rules", status_code=201)
async def add_geo_rule_endpoint(
    campaign_id: str,
    data: GeoRuleCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    rule_id = await add_geo_rule(campaign_id, data.model_dump(), db, redis)
    return {"success": True, "rule_id": rule_id}


@router.delete("/{campaign_id}/geo-rules/{rule_id}")
async def delete_geo_rule_endpoint(
    campaign_id: str,
    rule_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    deleted = await delete_geo_rule(rule_id, db, redis)
    if not deleted:
        raise NotFoundError("Geo rule")
    return {"success": True, "message": "Geo rule deleted"}


@router.post("/{campaign_id}/device-rules", status_code=201)
async def add_device_rule_endpoint(
    campaign_id: str,
    data: DeviceRuleCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    rule_id = await add_device_rule(campaign_id, data.model_dump(), db, redis)
    return {"success": True, "rule_id": rule_id}


@router.delete("/{campaign_id}/device-rules/{rule_id}")
async def delete_device_rule_endpoint(
    campaign_id: str,
    rule_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    deleted = await delete_device_rule(rule_id, db, redis)
    if not deleted:
        raise NotFoundError("Device rule")
    return {"success": True, "message": "Device rule deleted"}


@router.patch("/{campaign_id}/assign")
async def assign_campaign(
    campaign_id: str,
    data: AssignCampaignRequest,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Assign or unassign a campaign to a website."""
    try:
        oid = ObjectId(data.website_id)
    except Exception:
        oid = data.website_id
    result = await db.websites.update_one(
        {"_id": oid},
        {"$set": {"assigned_campaign_id": data.campaign_id, "updated_at": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        await db.websites.update_one(
            {"_id": data.website_id},
            {"$set": {"assigned_campaign_id": data.campaign_id, "updated_at": datetime.utcnow()}}
        )
    return {"success": True, "message": "Campaign assignment updated"}
