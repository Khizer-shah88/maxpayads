from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timedelta
from app.dependencies import get_db, get_current_admin
from app.utils.date_utils import timestamp_range_query
import csv
import io

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview")
async def analytics_overview(
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Platform-wide analytics overview."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_clicks = await db.clicks.count_documents({})
    valid_clicks = await db.clicks.count_documents({"is_valid": True})
    today_clicks = await db.clicks.count_documents({"timestamp": {"$gte": today_start}})
    month_clicks = await db.clicks.count_documents({"timestamp": {"$gte": month_start}})

    pipeline = [{"$match": {"is_valid": True}}, {"$group": {"_id": None, "total": {"$sum": "$earnings"}}}]
    result = await db.clicks.aggregate(pipeline).to_list(length=1)
    total_earnings = result[0]["total"] if result else 0.0

    return {
        "success": True,
        "overview": {
            "total_clicks": total_clicks,
            "valid_clicks": valid_clicks,
            "invalid_clicks": total_clicks - valid_clicks,
            "today_clicks": today_clicks,
            "month_clicks": month_clicks,
            "total_earnings": round(total_earnings, 4),
            "fraud_rate": round((1 - valid_clicks / max(total_clicks, 1)) * 100, 2),
        }
    }


@router.get("/clicks-trend")
async def clicks_trend(
    period: str = Query("7d", description="7d, 30d, 90d"),
    publisher_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get daily click trends."""
    days_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
    days = days_map.get(period, 7)
    if days == 1:
        since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        since = datetime.utcnow() - timedelta(days=days)

    match_query = {"timestamp": {"$gte": since}}
    if publisher_id:
        match_query["publisher_id"] = publisher_id

    pipeline = [
        {"$match": match_query},
        {
            "$group": {
                "_id": {
                    "year": {"$year": "$timestamp"},
                    "month": {"$month": "$timestamp"},
                    "day": {"$dayOfMonth": "$timestamp"},
                },
                "clicks": {"$sum": 1},
                "valid_clicks": {"$sum": {"$cond": ["$is_valid", 1, 0]}},
                "invalid_clicks": {"$sum": {"$cond": [{"$not": "$is_valid"}, 1, 0]}},
                "earnings": {"$sum": "$earnings"},
            }
        },
        {"$sort": {"_id.year": 1, "_id.month": 1, "_id.day": 1}},
    ]
    results = await db.clicks.aggregate(pipeline).to_list(length=None)

    trend = []
    for r in results:
        d = r["_id"]
        trend.append({
            "date": f"{d['year']}-{d['month']:02d}-{d['day']:02d}",
            "clicks": r["clicks"],
            "valid_clicks": r["valid_clicks"],
            "invalid_clicks": r["invalid_clicks"],
            "earnings": round(r["earnings"], 4),
        })

    return {"success": True, "trend": trend, "period": period}


@router.get("/top-countries")
async def top_countries(
    days: int = Query(30),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get top countries by click volume."""
    since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) if days == 1 else datetime.utcnow() - timedelta(days=days)
    pipeline = [
        {"$match": {"timestamp": {"$gte": since}, "country_code": {"$exists": True, "$ne": None}}},
        {
            "$group": {
                "_id": {"code": "$country_code", "name": "$country_name"},
                "clicks": {"$sum": 1},
                "valid_clicks": {"$sum": {"$cond": ["$is_valid", 1, 0]}},
                "earnings": {"$sum": "$earnings"},
            }
        },
        {"$sort": {"clicks": -1}},
        {"$limit": 20},
    ]
    results = await db.clicks.aggregate(pipeline).to_list(length=None)
    countries = [
        {
            "country_code": r["_id"]["code"],
            "country_name": r["_id"]["name"] or r["_id"]["code"],
            "clicks": r["clicks"],
            "valid_clicks": r["valid_clicks"],
            "earnings": round(r["earnings"], 4),
        }
        for r in results
    ]
    return {"success": True, "countries": countries}


@router.get("/top-publishers")
async def top_publishers(
    days: int = Query(30),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get top publishers by earnings."""
    since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) if days == 1 else datetime.utcnow() - timedelta(days=days)
    pipeline = [
        {"$match": {"timestamp": {"$gte": since}, "is_valid": True}},
        {
            "$group": {
                "_id": "$publisher_id",
                "total_clicks": {"$sum": 1},
                "total_earnings": {"$sum": "$earnings"},
            }
        },
        {"$sort": {"total_earnings": -1}},
        {"$limit": 10},
    ]
    results = await db.clicks.aggregate(pipeline).to_list(length=None)

    publishers = []
    for r in results:
        pub = await db.publishers.find_one({"_id": r["_id"]})
        if not pub:
            try:
                from bson import ObjectId as OId
                pub = await db.publishers.find_one({"_id": OId(r["_id"])})
            except Exception:
                pass
        if not pub:
            continue
        publishers.append({
            "publisher_id": r["_id"],
            "name": pub["name"],
            "email": pub.get("email", ""),
            "total_clicks": r["total_clicks"],
            "total_earnings": round(r["total_earnings"], 4),
        })

    return {"success": True, "publishers": publishers}


@router.get("/fraud-stats")
async def fraud_stats(
    days: int = Query(30),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get fraud detection statistics."""
    since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) if days == 1 else datetime.utcnow() - timedelta(days=days)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    total_fraud = await db.fraud_logs.count_documents({"detected_at": {"$gte": since}})
    today_fraud = await db.fraud_logs.count_documents({"detected_at": {"$gte": today_start}})

    # Fraud by reason
    pipeline = [
        {"$match": {"detected_at": {"$gte": since}}},
        {"$group": {"_id": "$fraud_reason", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    reasons = await db.fraud_logs.aggregate(pipeline).to_list(length=None)
    fraud_by_reason = {r["_id"]: r["count"] for r in reasons}

    # Top fraud IPs
    ip_pipeline = [
        {"$match": {"detected_at": {"$gte": since}}},
        {"$group": {"_id": "$ip_address", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_ips = await db.fraud_logs.aggregate(ip_pipeline).to_list(length=None)

    total_clicks = await db.clicks.count_documents({"timestamp": {"$gte": since}})
    fraud_rate = round((total_fraud / max(total_clicks, 1)) * 100, 2)

    return {
        "success": True,
        "stats": {
            "total_fraud": total_fraud,
            "today_fraud": today_fraud,
            "fraud_by_reason": fraud_by_reason,
            "fraud_rate": fraud_rate,
            "top_fraud_ips": [{"ip": r["_id"], "count": r["count"]} for r in top_ips],
        }
    }


@router.delete("/fraud-clicks/by-reason")
async def delete_fraud_by_reason(
    reason: str = Query(...),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Delete all fraud logs for a specific reason."""
    result = await db.fraud_logs.delete_many({"fraud_reason": reason})
    await db.clicks.delete_many({"fraud_reason": reason, "is_valid": False})
    return {"success": True, "deleted": result.deleted_count}


@router.delete("/fraud-clicks/by-ip")
async def delete_fraud_by_ip(
    ip: str = Query(...),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Delete all fraud logs for a specific IP."""
    result = await db.fraud_logs.delete_many({"ip_address": ip})
    await db.clicks.delete_many({"ip_address": ip, "is_valid": False})
    return {"success": True, "deleted": result.deleted_count}


@router.get("/distribution")
async def click_distribution(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    days: Optional[int] = Query(None, description="Number of days to look back (7, 30, or None for lifetime)"),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get OS and device distribution for a specific date, date range, or lifetime."""
    if days is not None:
        if days == 1:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            since = datetime.utcnow() - timedelta(days=days)
        match_q = {"timestamp": {"$gte": since}}
    elif date:
        try:
            day_start = datetime.fromisoformat(date)
        except Exception:
            day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        match_q = {"timestamp": {"$gte": day_start, "$lt": day_end}}
    else:
        match_q = {}

    # OS distribution
    os_pipeline = [
        {"$match": match_q},
        {"$group": {"_id": "$os", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    os_results = await db.clicks.aggregate(os_pipeline).to_list(length=None)

    OS_COLORS = {"Windows": "#3B82F6", "Mac": "#6B7280", "Mac OS X": "#6B7280", "macOS": "#6B7280", "Android": "#10B981", "iOS": "#F97316", "Linux": "#8B5CF6"}
    os_distribution = [
        {"label": r["_id"] or "Unknown", "value": r["count"], "color": OS_COLORS.get(r["_id"] or "", "#9CA3AF")}
        for r in os_results if r["_id"]
    ]

    # Device distribution
    device_pipeline = [
        {"$match": match_q},
        {"$group": {"_id": "$device_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    device_results = await db.clicks.aggregate(device_pipeline).to_list(length=None)

    DEVICE_COLORS = {"desktop": "#1E293B", "Desktop": "#1E293B", "mobile": "#10B981", "Mobile": "#10B981", "tablet": "#F59E0B", "Tablet": "#F59E0B"}
    device_distribution = [
        {"label": (r["_id"] or "Unknown").capitalize(), "value": r["count"], "color": DEVICE_COLORS.get(r["_id"] or "", "#9CA3AF")}
        for r in device_results if r["_id"]
    ]

    return {
        "success": True,
        "os_distribution": os_distribution,
        "device_distribution": device_distribution,
        "date": date or (days and f"last_{days}_days") or datetime.utcnow().strftime("%Y-%m-%d"),
    }


@router.get("/click-stats")
async def click_stats(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    publisher_id: Optional[str] = Query(None),
    website_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    country_code: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    os: Optional[str] = Query(None),
    browser: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get aggregate click statistics (totals + daily trend) for the statistics page."""
    query: dict = {}
    if publisher_id:
        query["publisher_id"] = publisher_id
    if website_id:
        query["website_id"] = website_id
    if status:
        query["status"] = status
    if country_code:
        query["country_code"] = country_code.upper()
    if device_type:
        query["device_type"] = device_type
    if os:
        query["os"] = {"$regex": os, "$options": "i"}
    if browser:
        query["browser"] = {"$regex": browser, "$options": "i"}
    tr = timestamp_range_query(date_from, date_to)
    if tr:
        query["timestamp"] = tr

    # Totals
    total = await db.clicks.count_documents(query)
    valid = await db.clicks.count_documents({**query, "status": "valid"}) if not status else (total if status == "valid" else 0)
    invalid = await db.clicks.count_documents({**query, "status": "invalid"}) if not status else (total if status == "invalid" else 0)

    earnings_pipeline = [
        {"$match": query},
        {"$group": {"_id": None, "total": {"$sum": "$earnings"}}},
    ]
    e_result = await db.clicks.aggregate(earnings_pipeline).to_list(length=1)
    earnings = e_result[0]["total"] if e_result else 0.0

    # Daily trend
    trend_pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": {
                    "year": {"$year": "$timestamp"},
                    "month": {"$month": "$timestamp"},
                    "day": {"$dayOfMonth": "$timestamp"},
                },
                "valid": {"$sum": {"$cond": [{"$eq": ["$status", "valid"]}, 1, 0]}},
                "invalid": {"$sum": {"$cond": [{"$eq": ["$status", "invalid"]}, 1, 0]}},
                "earnings": {"$sum": "$earnings"},
            }
        },
        {"$sort": {"_id.year": 1, "_id.month": 1, "_id.day": 1}},
    ]
    trend_results = await db.clicks.aggregate(trend_pipeline).to_list(length=None)
    daily_trend = []
    for r in trend_results:
        d = r["_id"]
        daily_trend.append({
            "date": f"{d['month']:02d}/{d['day']:02d}",
            "valid": r["valid"],
            "invalid": r["invalid"],
            "earnings": round(r["earnings"], 4),
        })

    # Distribution breakdowns computed over the FULL filtered set (so the pies
    # reflect every matching click, not just the current page of 50 rows).
    async def _distribution(field: str, limit: Optional[int] = None):
        pipe = [
            {"$match": query},
            {"$group": {"_id": f"${field}", "value": {"$sum": 1}}},
            {"$sort": {"value": -1}},
        ]
        if limit:
            pipe.append({"$limit": limit})
        rows = await db.clicks.aggregate(pipe).to_list(length=None)
        return [{"name": (r["_id"] or "Unknown"), "value": r["value"]} for r in rows]

    distribution = {
        "devices": await _distribution("device_type"),
        "os": await _distribution("os"),
        "browsers": await _distribution("browser"),
        "countries": await _distribution("country_code", limit=15),
    }

    return {
        "success": True,
        "totals": {"total": total, "valid": valid, "invalid": invalid, "earnings": round(earnings, 4)},
        "daily_trend": daily_trend,
        "distribution": distribution,
    }


@router.get("/export-csv")
async def export_analytics_csv(
    days: int = Query(30),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Export analytics data as CSV."""
    since = datetime.utcnow() - timedelta(days=days)
    pipeline = [
        {"$match": {"timestamp": {"$gte": since}}},
        {
            "$group": {
                "_id": {
                    "year": {"$year": "$timestamp"},
                    "month": {"$month": "$timestamp"},
                    "day": {"$dayOfMonth": "$timestamp"},
                },
                "clicks": {"$sum": 1},
                "valid": {"$sum": {"$cond": ["$is_valid", 1, 0]}},
                "earnings": {"$sum": "$earnings"},
            }
        },
        {"$sort": {"_id.year": 1, "_id.month": 1, "_id.day": 1}},
    ]
    results = await db.clicks.aggregate(pipeline).to_list(length=None)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Total Clicks", "Valid Clicks", "Invalid Clicks", "Earnings"])
    for r in results:
        d = r["_id"]
        date_str = f"{d['year']}-{d['month']:02d}-{d['day']:02d}"
        writer.writerow([date_str, r["clicks"], r["valid"], r["clicks"] - r["valid"], round(r["earnings"], 4)])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=analytics.csv"},
    )
