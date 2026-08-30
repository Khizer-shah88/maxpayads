from datetime import datetime, timedelta
from typing import List, Optional
from bson import ObjectId
from app.core.security import hash_password
import logging

logger = logging.getLogger(__name__)


def _oid(id_str: str):
    """Return ObjectId if valid, otherwise fall back to string (for admin_001 etc.)."""
    try:
        return ObjectId(id_str)
    except Exception:
        return id_str


async def create_publisher(data: dict, db) -> str:
    data["password_hash"] = hash_password(data.pop("password"))
    data["role"] = "publisher"
    data["status"] = "pending"
    data["balance"] = 0.0
    data["total_earnings"] = 0.0
    data["total_clicks"] = 0
    data["valid_clicks"] = 0
    data["invalid_clicks"] = 0
    data["revenue_share"] = 0.80
    data["created_at"] = datetime.utcnow()
    data["updated_at"] = datetime.utcnow()
    result = await db.publishers.insert_one(data)
    return str(result.inserted_id)


async def get_publisher_by_email(email: str, db) -> Optional[dict]:
    publisher = await db.publishers.find_one({"email": email})
    if publisher:
        publisher["id"] = str(publisher.pop("_id"))
    return publisher


async def get_publisher_by_id(publisher_id: str, db) -> Optional[dict]:
    publisher = await db.publishers.find_one({"_id": _oid(publisher_id)})
    if not publisher:
        publisher = await db.publishers.find_one({"_id": publisher_id})
    if publisher:
        publisher["id"] = str(publisher.pop("_id"))
    return publisher


async def get_all_publishers(db, status: Optional[str] = None, skip: int = 0, limit: int = 50) -> List[dict]:
    query = {"role": "publisher"}  # never return admin accounts in the publisher list
    if status:
        query["status"] = status
    cursor = db.publishers.find(query).skip(skip).limit(limit).sort("created_at", -1)
    publishers = await cursor.to_list(length=None)
    for p in publishers:
        p["id"] = str(p.pop("_id"))
        p.pop("password_hash", None)
        for key in ("created_at", "updated_at"):
            if isinstance(p.get(key), datetime):
                p[key] = p[key].isoformat()
    return publishers


async def count_publishers(db, status: Optional[str] = None) -> int:
    query = {"role": "publisher"}
    if status:
        query["status"] = status
    return await db.publishers.count_documents(query)


async def update_publisher(publisher_id: str, data: dict, db) -> bool:
    data["updated_at"] = datetime.utcnow()
    result = await db.publishers.update_one(
        {"_id": _oid(publisher_id)}, {"$set": data}
    )
    if result.matched_count == 0:
        result = await db.publishers.update_one(
            {"_id": publisher_id}, {"$set": data}
        )
    return result.modified_count > 0


async def delete_publisher_and_records(publisher_id: str, db) -> bool:
    """Delete publisher and all associated records from DB."""
    await db.clicks.delete_many({"publisher_id": publisher_id})
    await db.withdrawals.delete_many({"publisher_id": publisher_id})
    await db.fraud_logs.delete_many({"publisher_id": publisher_id})
    websites = await db.websites.find({"publisher_id": publisher_id}).to_list(length=None)
    for w in websites:
        await db.websites.delete_one({"_id": w["_id"]})
    result = await db.publishers.delete_one({"_id": _oid(publisher_id)})
    if result.deleted_count == 0:
        result = await db.publishers.delete_one({"_id": publisher_id})
    return result.deleted_count > 0


async def get_publisher_stats(publisher_id: str, db) -> dict:
    """Calculate comprehensive publisher statistics."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    publisher = await db.publishers.find_one({"_id": _oid(publisher_id)})
    if not publisher:
        publisher = await db.publishers.find_one({"_id": publisher_id})
    if not publisher:
        return {}

    today_clicks = await db.clicks.count_documents({
        "publisher_id": publisher_id,
        "timestamp": {"$gte": today_start}
    })
    today_valid = await db.clicks.count_documents({
        "publisher_id": publisher_id,
        "timestamp": {"$gte": today_start},
        "is_valid": True
    })
    today_invalid = today_clicks - today_valid

    pipeline_today = [
        {"$match": {"publisher_id": publisher_id, "timestamp": {"$gte": today_start}, "is_valid": True}},
        {"$group": {"_id": None, "total": {"$sum": "$earnings"}}}
    ]
    result = await db.clicks.aggregate(pipeline_today).to_list(length=1)
    today_earnings = result[0]["total"] if result else 0.0

    month_clicks = await db.clicks.count_documents({
        "publisher_id": publisher_id,
        "timestamp": {"$gte": month_start}
    })
    pipeline_month = [
        {"$match": {"publisher_id": publisher_id, "timestamp": {"$gte": month_start}, "is_valid": True}},
        {"$group": {"_id": None, "total": {"$sum": "$earnings"}}}
    ]
    result_m = await db.clicks.aggregate(pipeline_month).to_list(length=1)
    month_earnings = result_m[0]["total"] if result_m else 0.0

    return {
        "today_clicks": today_clicks,
        "today_earnings": round(today_earnings, 4),
        "today_valid_clicks": today_valid,
        "today_invalid_clicks": today_invalid,
        "total_clicks": publisher.get("total_clicks", 0),
        "total_earnings": publisher.get("total_earnings", 0.0),
        "valid_clicks": publisher.get("valid_clicks", 0),
        "invalid_clicks": publisher.get("invalid_clicks", 0),
        "balance": publisher.get("balance", 0.0),
        "this_month_clicks": month_clicks,
        "this_month_earnings": round(month_earnings, 4),
    }
