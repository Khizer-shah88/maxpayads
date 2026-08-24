from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timedelta
from app.schemas.publisher_schema import AdminPublisherUpdate, BalanceAdjustment
from app.services.publisher_service import (
    get_all_publishers, get_publisher_by_id, update_publisher,
    delete_publisher_and_records, count_publishers, get_publisher_stats,
)
from app.services.earnings_service import adjust_publisher_balance
from app.services.cpc_engine import get_global_cpc_settings, set_country_cpc, delete_country_cpc
from app.dependencies import get_db, get_current_admin
from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.security import verify_password, hash_password
from app.utils.date_utils import timestamp_range_query
from bson import ObjectId
import csv
import io

# Effectively "no cap" for record/export sweeps that must include every publisher.
RECORDS_PUBLISHER_LIMIT = 1_000_000

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/dashboard")
async def admin_dashboard(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    days: Optional[int] = Query(None, description="Number of days to look back (7, 30, or None for lifetime)"),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get platform-wide admin dashboard statistics."""
    now = datetime.utcnow()

    # Build time filter based on days parameter
    if days is not None:
        if days == 1:
            # "Daily" = from start of today (midnight UTC)
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            since = now - timedelta(days=days)
        time_filter = {"timestamp": {"$gte": since}}
    elif date:
        try:
            day_start = datetime.fromisoformat(date)
        except Exception:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        time_filter = {"timestamp": {"$gte": day_start}}
    else:
        time_filter = {}

    # All click stats filtered by the selected period
    total_clicks = await db.clicks.count_documents(time_filter)
    valid_clicks = await db.clicks.count_documents({**time_filter, "is_valid": True})
    invalid_clicks = await db.clicks.count_documents({**time_filter, "is_valid": False, "status": "invalid"})
    fraud_clicks = await db.fraud_logs.count_documents(time_filter if time_filter else {})

    total_publishers = await db.publishers.count_documents({"role": "publisher"})
    active_publishers = await db.publishers.count_documents({"role": "publisher", "status": "active"})
    pending_publishers = await db.publishers.count_documents({"role": "publisher", "status": "pending"})

    # Earnings filtered by the selected period
    earnings_match = {**time_filter, "is_valid": True} if time_filter else {"is_valid": True}
    pipeline = [{"$match": earnings_match}, {"$group": {"_id": None, "total": {"$sum": "$earnings"}}}]
    result = await db.clicks.aggregate(pipeline).to_list(length=1)
    total_earnings = result[0]["total"] if result else 0.0

    pending_withdrawals = await db.withdrawals.count_documents({"status": "pending"})
    wd_pipeline = [
        {"$match": {"status": "pending"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    wd_result = await db.withdrawals.aggregate(wd_pipeline).to_list(length=1)
    pending_wd_amount = wd_result[0]["total"] if wd_result else 0.0

    fraud_rate = round((fraud_clicks / total_clicks * 100) if total_clicks > 0 else 0.0, 2)

    return {
        "success": True,
        "stats": {
            "total_clicks": total_clicks,
            "valid_clicks": valid_clicks,
            "invalid_clicks": invalid_clicks,
            "fraud_clicks": fraud_clicks,
            "total_publishers": total_publishers,
            "active_publishers": active_publishers,
            "pending_publishers": pending_publishers,
            "total_earnings": round(total_earnings, 4),
            "fraud_rate": fraud_rate,
            "pending_withdrawals": pending_withdrawals,
            "pending_withdrawal_amount": round(pending_wd_amount, 2),
        }
    }


@router.get("/publishers")
async def list_publishers(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    skip = (page - 1) * limit
    publishers = await get_all_publishers(db, status=status, skip=skip, limit=limit)
    total = await count_publishers(db, status=status)
    return {
        "success": True,
        "publishers": publishers,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/publishers/{publisher_id}")
async def get_publisher(
    publisher_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    publisher = await get_publisher_by_id(publisher_id, db)
    if not publisher:
        raise NotFoundError("Publisher")
    publisher.pop("password_hash", None)
    stats = await get_publisher_stats(publisher_id, db)
    return {"success": True, "publisher": publisher, "stats": stats}


@router.patch("/publishers/{publisher_id}")
async def update_publisher_endpoint(
    publisher_id: str,
    data: AdminPublisherUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        return {"success": True, "message": "No changes"}
    updated = await update_publisher(publisher_id, update_data, db)
    if not updated:
        raise NotFoundError("Publisher")
    return {"success": True, "message": "Publisher updated"}


@router.delete("/publishers/{publisher_id}")
async def delete_publisher(
    publisher_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    deleted = await delete_publisher_and_records(publisher_id, db)
    if not deleted:
        raise NotFoundError("Publisher")
    return {"success": True, "message": "Publisher and all records deleted"}


@router.post("/publishers/{publisher_id}/balance")
async def adjust_balance(
    publisher_id: str,
    data: BalanceAdjustment,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    await adjust_publisher_balance(publisher_id, data.amount, db)
    return {"success": True, "message": f"Balance adjusted by ${data.amount:.2f}"}


@router.get("/publishers/{publisher_id}/download-csv")
async def download_publisher_csv(
    publisher_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Download complete publisher data as CSV."""
    publisher = await get_publisher_by_id(publisher_id, db)
    if not publisher:
        raise NotFoundError("Publisher")

    cursor = db.clicks.find({"publisher_id": publisher_id}).sort("timestamp", -1)
    clicks = await cursor.to_list(length=None)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Publisher Report"])
    writer.writerow(["Name", publisher.get("name"), "Email", publisher.get("email")])
    writer.writerow(["Status", publisher.get("status"), "Balance", f"${publisher.get('balance', 0):.2f}"])
    writer.writerow([])
    writer.writerow(["Click ID", "Timestamp", "IP", "Country", "Device", "OS", "Status", "CPC", "Earnings", "Fraud Reason"])
    for c in clicks:
        writer.writerow([
            str(c.get("_id")), str(c.get("timestamp")), c.get("ip_address"),
            c.get("country_code"), c.get("device_type"), c.get("os"),
            c.get("status"), c.get("cpc", 0), c.get("earnings", 0), c.get("fraud_reason", ""),
        ])

    output.seek(0)
    filename = f"publisher_{publisher_id}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/websites")
async def get_all_websites(
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get all websites across all publishers."""
    cursor = db.websites.find({})
    websites = await cursor.to_list(length=None)
    for w in websites:
        w["id"] = str(w.pop("_id", ""))
        if w.get("created_at"):
            w["created_at"] = w["created_at"].isoformat()
        if w.get("updated_at"):
            w["updated_at"] = w["updated_at"].isoformat()
    return {"success": True, "websites": websites}


@router.get("/records")
async def get_records(
    days: int = Query(30, description="Number of days to filter"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get publisher records with date filtering for history page."""
    # Build an inclusive time filter from an explicit from/to range, or fall
    # back to the "last N days" window. Works with either or both bounds set.
    tr = timestamp_range_query(date_from, date_to)
    if not tr:
        _until = datetime.utcnow()
        _since = _until - timedelta(days=days)
        tr = {"$gte": _since, "$lte": _until}
    since = tr.get("$gte")
    if tr.get("$lte"):
        until = tr.get("$lte")
    elif tr.get("$lt"):
        # $lt is the exclusive next-midnight bound; show the inclusive last day.
        until = tr.get("$lt") - timedelta(days=1)
    else:
        until = datetime.utcnow()

    # Get all publishers (no 50-row cap — records must cover everyone)
    publishers = await get_all_publishers(db, limit=RECORDS_PUBLISHER_LIMIT)
    records = []

    for pub in publishers:
        pub_id = pub["id"]
        # Get click stats for this publisher in date range
        query = {"publisher_id": pub_id, "timestamp": tr}
        total_clicks = await db.clicks.count_documents(query)
        # Valid/invalid by status so Records reconciles with Statistics/Dashboard
        # (total - is_valid would wrongly fold "pending" clicks into invalid).
        valid_clicks = await db.clicks.count_documents({**query, "status": "valid"})
        invalid_clicks = await db.clicks.count_documents({**query, "status": "invalid"})

        pipeline = [
            {"$match": {**query, "is_valid": True}},
            {"$group": {"_id": None, "total": {"$sum": "$earnings"}}}
        ]
        result = await db.clicks.aggregate(pipeline).to_list(length=1)
        earnings = result[0]["total"] if result else 0.0

        # Get websites
        websites_cursor = db.websites.find({"publisher_id": pub_id})
        websites = await websites_cursor.to_list(length=None)
        for w in websites:
            w["id"] = str(w.pop("_id", ""))
            if w.get("created_at"):
                w["created_at"] = w["created_at"].isoformat()
            if w.get("updated_at"):
                w["updated_at"] = w["updated_at"].isoformat()

        # Withdrawal history
        wd_cursor = db.withdrawals.find({"publisher_id": pub_id, "requested_at": tr})
        withdrawals = await wd_cursor.to_list(length=None)
        for wd in withdrawals:
            wd["id"] = str(wd.pop("_id", ""))
            if wd.get("requested_at"):
                wd["requested_at"] = wd["requested_at"].isoformat()
            if wd.get("processed_at"):
                wd["processed_at"] = wd["processed_at"].isoformat()

        records.append({
            "publisher": pub,
            "websites": websites,
            "stats": {
                "total_clicks": total_clicks,
                "valid_clicks": valid_clicks,
                "invalid_clicks": invalid_clicks,
                "earnings": round(earnings, 4),
            },
            "withdrawals": withdrawals,
        })

    return {
        "success": True,
        "records": records,
        "date_range": {
            "from": since.isoformat() if since else None,
            "to": until.isoformat() if until else None,
        },
    }


@router.get("/records/export-csv")
async def export_records_csv(
    days: int = Query(30),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Export all records as CSV, honoring the same date range as the page."""
    tr = timestamp_range_query(date_from, date_to)
    if not tr:
        _until = datetime.utcnow()
        _since = _until - timedelta(days=days)
        tr = {"$gte": _since, "$lte": _until}
    since = tr.get("$gte")
    if tr.get("$lte"):
        until = tr.get("$lte")
    elif tr.get("$lt"):
        # $lt is the exclusive next-midnight bound; show the inclusive last day.
        until = tr.get("$lt") - timedelta(days=1)
    else:
        until = datetime.utcnow()
    if since:
        period = f"{since.strftime('%Y-%m-%d')} to {until.strftime('%Y-%m-%d')}"
    else:
        period = f"through {until.strftime('%Y-%m-%d')}"

    publishers = await get_all_publishers(db, limit=RECORDS_PUBLISHER_LIMIT)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Publisher Name", "Email", "Status", "Website", "Total Clicks",
        "Valid Clicks", "Invalid Clicks", "Earnings", "Balance", "Period"
    ])

    for pub in publishers:
        pub_id = pub["id"]
        query = {"publisher_id": pub_id, "timestamp": tr}
        total_clicks = await db.clicks.count_documents(query)
        valid_clicks = await db.clicks.count_documents({**query, "status": "valid"})
        invalid_clicks = await db.clicks.count_documents({**query, "status": "invalid"})
        pipeline = [
            {"$match": {**query, "is_valid": True}},
            {"$group": {"_id": None, "total": {"$sum": "$earnings"}}}
        ]
        result = await db.clicks.aggregate(pipeline).to_list(length=1)
        earnings = result[0]["total"] if result else 0.0

        websites_cursor = db.websites.find({"publisher_id": pub_id})
        websites = await websites_cursor.to_list(length=None)
        website_domains = ", ".join(w.get("domain", "") for w in websites)

        writer.writerow([
            pub.get("name"), pub.get("email"), pub.get("status"),
            website_domains, total_clicks, valid_clicks, invalid_clicks,
            round(earnings, 4), round(pub.get("balance", 0), 2),
            period,
        ])

    output.seek(0)
    filename = f"records_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/videos")
async def admin_get_videos(
    publisher_id: Optional[str] = Query(None),
    website_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get all publisher videos with optional publisher, website, and status filters."""
    query = {}
    if publisher_id:
        query["publisher_id"] = publisher_id
    if website_id:
        query["website_id"] = website_id
    if status:
        query["status"] = status

    cursor = db.publisher_videos.find(query).sort("created_at", -1)
    videos = await cursor.to_list(length=None)

    # Collect publisher IDs to resolve names
    pub_ids = list(set(v.get("publisher_id") for v in videos if v.get("publisher_id")))
    pub_map = {}
    if pub_ids:
        obj_ids = []
        for pid in pub_ids:
            try:
                obj_ids.append(ObjectId(pid))
            except Exception:
                pass
        if obj_ids:
            pcursor = db.publishers.find({"_id": {"$in": obj_ids}}, {"name": 1, "email": 1})
            async for p in pcursor:
                pub_map[str(p["_id"])] = {"name": p.get("name", ""), "email": p.get("email", "")}

    # Resolve website_id -> domain
    website_ids = list(set(v.get("website_id") for v in videos if v.get("website_id")))
    website_map = {}
    if website_ids:
        w_obj_ids = []
        for wid in website_ids:
            try:
                w_obj_ids.append(ObjectId(wid))
            except Exception:
                pass
        if w_obj_ids:
            wcursor = db.websites.find({"_id": {"$in": w_obj_ids}}, {"domain": 1})
            async for w in wcursor:
                website_map[str(w["_id"])] = w.get("domain", "")

    for v in videos:
        v["id"] = str(v.pop("_id"))
        pub_info = pub_map.get(v.get("publisher_id"), {})
        v["publisher_name"] = pub_info.get("name", "Unknown")
        v["publisher_email"] = pub_info.get("email", "")
        v["website_domain"] = website_map.get(v.get("website_id", ""), "")
        if v.get("created_at"):
            v["created_at"] = v["created_at"].isoformat() if hasattr(v["created_at"], "isoformat") else str(v["created_at"])

    return {"success": True, "videos": videos, "total": len(videos)}


@router.patch("/videos/{video_id}")
async def admin_update_video(
    video_id: str,
    data: dict,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Update a video's status (approve/reject)."""
    update_fields = {}
    if "status" in data:
        if data["status"] not in ("active", "rejected", "pending"):
            raise HTTPException(status_code=400, detail="Invalid status")
        update_fields["status"] = data["status"]
    if not update_fields:
        return {"success": True, "message": "No changes"}
    try:
        oid = ObjectId(video_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid video ID")
    result = await db.publisher_videos.update_one({"_id": oid}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"success": True, "message": f"Video status updated to {update_fields.get('status', '')}"}


@router.delete("/videos/{video_id}")
async def admin_delete_video(
    video_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Delete a publisher video."""
    try:
        oid = ObjectId(video_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid video ID")
    result = await db.publisher_videos.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"success": True, "message": "Video deleted"}


@router.get("/settings")
async def get_settings(
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    cpc_settings = await get_global_cpc_settings(db)
    other_cursor = db.system_settings.find({"key": {"$not": {"$regex": "^cpc_"}}})
    other_settings = await other_cursor.to_list(length=None)
    for s in other_settings:
        s["id"] = str(s.pop("_id", ""))

    # Get platform domain setting
    domain_doc = await db.system_settings.find_one({"key": "platform_domain"})
    platform_domain = domain_doc.get("value", "") if domain_doc else ""

    return {"success": True, "cpc_settings": cpc_settings, "other_settings": other_settings, "platform_domain": platform_domain}


@router.get("/domain")
async def get_domain(
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get the configured platform domain."""
    doc = await db.system_settings.find_one({"key": "platform_domain"})
    domain = doc.get("value", "") if doc else ""
    return {"success": True, "domain": domain}


@router.put("/domain")
async def set_domain(
    data: dict,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Set the platform domain (used in ad embed codes)."""
    domain = data.get("domain", "").strip().rstrip("/")
    await db.system_settings.update_one(
        {"key": "platform_domain"},
        {"$set": {"key": "platform_domain", "value": domain, "updated_at": datetime.utcnow()}},
        upsert=True,
    )
    return {"success": True, "message": "Domain updated", "domain": domain}


@router.put("/settings/cpc/bulk")
async def bulk_update_cpc(
    data: dict,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Set CPC for multiple countries at once."""
    countries = data.get("countries", [])
    cpc = float(data.get("cpc", 0))
    if not countries or cpc <= 0:
        return {"success": False, "message": "Countries list and valid CPC are required"}
    for cc in countries:
        await set_country_cpc(cc.upper(), cpc, db)
    return {"success": True, "message": f"CPC updated for {len(countries)} countries"}


@router.put("/settings/cpc/{country_code}")
async def update_cpc_setting(
    country_code: str,
    data: dict,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    try:
        cpc = float(data.get("cpc"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="A numeric 'cpc' value is required")
    if cpc <= 0:
        raise HTTPException(status_code=400, detail="'cpc' must be greater than 0")
    await set_country_cpc(country_code.upper(), cpc, db)
    return {"success": True, "message": f"CPC for {country_code} updated"}


@router.delete("/settings/cpc/{country_code}")
async def delete_cpc_setting(
    country_code: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    await delete_country_cpc(country_code.upper(), db)
    return {"success": True, "message": f"CPC override for {country_code} removed"}


@router.post("/change-password")
async def change_password(
    data: dict,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Change admin password."""
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Current and new password are required")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    if not verify_password(current_password, current_user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    new_hash = hash_password(new_password)
    await db.publishers.update_one(
        {"_id": ObjectId(current_user["id"]) if not isinstance(current_user["id"], ObjectId) else current_user["id"]},
        {"$set": {"password_hash": new_hash, "updated_at": datetime.utcnow()}},
    )
    return {"success": True, "message": "Password changed successfully"}
