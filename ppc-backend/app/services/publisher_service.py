from datetime import datetime, timedelta
from typing import List, Optional
from bson import ObjectId
from app.core.security import hash_password
from starlette.concurrency import run_in_threadpool
import logging
import secrets
import hashlib

logger = logging.getLogger(__name__)


def _oid(id_str: str):
    """Return ObjectId if valid, otherwise fall back to string (for admin_001 etc.)."""
    try:
        return ObjectId(id_str)
    except Exception:
        return id_str


def _generate_auto_email(name: str) -> str:
    """Generate a unique placeholder email for admin-created publishers (name-only creation)."""
    slug = hashlib.sha256(f"{name}{secrets.token_hex(4)}".encode()).hexdigest()[:12]
    safe = name.lower().replace(" ", "").replace(".", "")[:16]
    return f"pub.{safe}.{slug}@auto.invalid"


def _generate_auto_password() -> str:
    """Generate a secure random placeholder password."""
    return secrets.token_urlsafe(24)


async def create_publisher(data: dict, db, admin_id: Optional[str] = None) -> str:
    """
    Create a new publisher account.

    Supports name-only creation: if email or password are omitted, the system
    auto-generates placeholder values. The publisher_type is always "registered"
    (they can log in once credentials are shared), distinguishing them from
    "manual" publishers that can never log in.

    Args:
        data: Publisher data (name required; email/password optional)
        db: Database connection
        admin_id: If provided, marks publisher as admin-created

    Returns:
        Publisher ID string
    """
    from app.utils.public_id_utils import generate_unique_publisher_id

    name = (data.get("name") or "").strip()

    # Auto-generate email/password when not supplied (name-only creation)
    if not data.get("email"):
        data["email"] = _generate_auto_email(name)
    if not data.get("password"):
        data["password"] = _generate_auto_password()

    data["password_hash"] = await run_in_threadpool(hash_password, data.pop("password"))
    data["role"] = "publisher"
    # Admin-created publishers are active immediately; self-registered are pending.
    data["status"] = data.get("status", "active" if admin_id else "pending")
    data["publisher_type"] = data.get("publisher_type", "registered")
    data["balance"] = 0.0
    data["total_earnings"] = 0.0
    data["total_clicks"] = 0
    data["valid_clicks"] = 0
    data["invalid_clicks"] = 0
    # Default: 100% revenue share, 0.0 CPL
    data["revenue_share"] = data.get("revenue_share", 1.0)
    data["custom_cpc"] = float(data["custom_cpc"]) if data.get("custom_cpc") is not None else 0.0
    data["created_at"] = datetime.utcnow()
    data["updated_at"] = datetime.utcnow()

    # Generate unique public ID
    data["public_id"] = await generate_unique_publisher_id(db)

    # Admin-created tracking
    if admin_id:
        data["is_admin_created"] = True
        data["created_by"] = admin_id
    else:
        data["is_admin_created"] = False
        data["created_by"] = None

    result = await db.publishers.insert_one(data)
    return str(result.inserted_id)


async def create_manual_publisher(data: dict, db, admin_id: Optional[str] = None) -> str:
    """
    Create a Manual Publisher (Domain Glossary).

    A Manual Publisher is created directly by Admin with ONLY a unique
    Name/Tag. There is no login (no email/password), no website, and their
    Smartlink never carries a `site` parameter. The system auto-generates
    the Publisher ID (public_id PUB_XXXXXXXX) which is all the Smartlink needs.

    Returns the new publisher's internal _id string.
    """
    from app.utils.public_id_utils import generate_unique_publisher_id

    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("A unique Name/Tag is required")

    # Name/Tag must be unique among publishers.
    dup = await db.publishers.find_one({"name": name, "role": "publisher"})
    if dup:
        raise ValueError(f"Name/Tag '{name}' is already in use")

    now = datetime.utcnow()
    # Placeholder identity — manual publishers never log in, so the values are
    # random and inert; uniqueness keeps auth lookups from ever colliding.
    slug = secrets.token_hex(6)
    password_hash = await run_in_threadpool(hash_password, secrets.token_urlsafe(24))

    doc = {
        "name": name,
        "email": f"manual+{slug}@manual.invalid",
        "password_hash": password_hash,
        "role": "publisher",
        "status": "active",  # Admin-created: immediately routable
        "publisher_type": "manual",
        "revenue_share": float(data.get("revenue_share", 1.0)),  # Default 100%
        "custom_cpc": float(data["custom_cpc"]) if data.get("custom_cpc") else 0.0,  # Default 0.0
        "balance": 0.0,
        "total_earnings": 0.0,
        "total_clicks": 0,
        "valid_clicks": 0,
        "invalid_clicks": 0,
        "public_id": await generate_unique_publisher_id(db),
        "is_admin_created": True,
        "created_by": admin_id,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.publishers.insert_one(doc)
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


async def is_publisher_banned_or_removed(publisher_id: str, db) -> bool:
    """
    True when the publisher is banned or removed (or fully deleted).

    Publisher status rules (Domain Glossary):
      banned/removed → traffic still redirects, Admin Statistics still works,
                       but Direct Link Stats is UNAVAILABLE.
    A permanently deleted publisher resolves to True as well — there is no
    record left to show stats for.
    """
    from app.core.constants import PUB_BANNED, PUB_REMOVED
    publisher = await db.publishers.find_one({"_id": _oid(publisher_id)})
    if not publisher:
        publisher = await db.publishers.find_one({"_id": publisher_id})
    if not publisher:
        return True
    return publisher.get("status") in (PUB_BANNED, PUB_REMOVED)


async def get_all_publishers(db, status: Optional[str] = None, skip: int = 0, limit: int = 50) -> List[dict]:
    query = {"role": "publisher"}  # never return admin accounts in the publisher list
    if status:
        query["status"] = status
    cursor = db.publishers.find(query).skip(skip).limit(limit).sort("created_at", -1)
    publishers = await cursor.to_list(length=None)
    for p in publishers:
        p["id"] = str(p.pop("_id"))
        p.pop("password_hash", None)
        # Surface the glossary fields the admin UI relies on.
        p.setdefault("publisher_type", "registered")
        p.setdefault("public_id", None)
        p.setdefault("is_admin_created", False)
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
    """
    Delete a publisher AND every record attributed to them.

    The admin-reported bug ("clicks still showing on the publisher page after
    deletion") came from the old sweep deleting only clicks/withdrawals/
    fraud_logs by the STRING id, while several collections hold the publisher
    reference under other spellings and separate stats collections that the
    publishers list reads:

      - clicks / withdrawals / fraud_logs  → publisher_id: str | ObjectId
      - websites                            → publisher_id (+ their own rows)
      - direct_links                        → publisher_id (carries total_clicks/
                                              total_conversions counters the
                                              Direct Link Stats table reads)
      - direct_link_events                  → publisher_id (tracked events)
      - direct_link_manual_conversions      → publisher_id (admin-entered)
      - conversion_overrides                → publisher_id (manual overrides)
      - stats_profiles                      → publisher_id (whitelabel report)
      - stats_profile_clicks / _impressions /
        _conversions / _manual_conversions  → profile_id / publisher_slug keys
      - redirection_domains.publisher_ids   → membership (unassign, keep domain)

    Everything keyed by the publisher is removed in ONE sweep so no stats page
    can resurrect the deleted publisher's numbers.
    """
    # The same publisher id can exist as a string AND an ObjectId across
    # collections written at different times — sweep both spellings.
    id_match = {"$in": [publisher_id]}
    try:
        id_match["$in"].append(ObjectId(publisher_id))
    except Exception:
        pass  # not an ObjectId-shaped id — string form is all there is

    await db.clicks.delete_many({"publisher_id": id_match})
    await db.withdrawals.delete_many({"publisher_id": id_match})
    await db.fraud_logs.delete_many({"publisher_id": id_match})

    # Websites: try both spellings, then remove (no other owner).
    website_query = {"publisher_id": id_match}
    await db.websites.delete_many(website_query)

    # Direct link stats surfaces (the numbers the Direct Link Stats page reads).
    await db.direct_links.delete_many({"publisher_id": id_match})
    await db.direct_link_events.delete_many({"publisher_id": id_match})
    await db.direct_link_manual_conversions.delete_many({"publisher_id": id_match})
    try:
        await db.conversion_overrides.delete_many({"publisher_id": id_match})
    except Exception:
        pass  # collection not present in this deployment

    # Whitelabel stats profiles and their tracked events/clicks.
    profiles = await db.stats_profiles.find({"publisher_id": id_match}, {"_id": 1, "slug": 1}).to_list(length=None)
    for profile in profiles:
        profile_id = profile.get("_id")
        profile_slug = profile.get("slug")
        await db.stats_profile_clicks.delete_many({"profile_id": profile_id})
        await db.stats_profile_impressions.delete_many({"profile_id": profile_id})
        await db.stats_profile_conversions.delete_many({"profile_id": profile_id})
        if profile_slug:
            await db.stats_profile_manual_conversions.delete_many({"profile_slug": profile_slug})
    await db.stats_profiles.delete_many({"publisher_id": id_match})

    # Domain assignment: remove this publisher from every domain's member list.
    await db.redirection_domains.update_many(
        {"publisher_ids": {"$in": [publisher_id]}},
        {"$pull": {"publisher_ids": publisher_id}},
    )

    result = await db.publishers.delete_one({"_id": _oid(publisher_id)})
    if result.deleted_count == 0:
        result = await db.publishers.delete_one({"_id": publisher_id})
    return result.deleted_count > 0


async def delete_publisher_stats_only(publisher_id: str, db) -> dict:
    """
    Delete only statistics data for a publisher. The publisher account and
    websites remain intact.

    Same spelling coverage as delete_publisher_and_records (str + ObjectId ids)
    and the same additional collections — "delete the stats" must leave ZERO
    attributed numbers anywhere (the reported bug: clicks still showed after
    this action).

    Returns: Dictionary with count of deleted records
    """
    id_match = {"$in": [publisher_id]}
    try:
        id_match["$in"].append(ObjectId(publisher_id))
    except Exception:
        pass

    clicks_result = await db.clicks.delete_many({"publisher_id": id_match})
    withdrawals_result = await db.withdrawals.delete_many({"publisher_id": id_match})
    fraud_result = await db.fraud_logs.delete_many({"publisher_id": id_match})

    # Direct link stats surfaces
    links_result = await db.direct_links.delete_many({"publisher_id": id_match})
    events_result = await db.direct_link_events.delete_many({"publisher_id": id_match})
    manual_result = await db.direct_link_manual_conversions.delete_many({"publisher_id": id_match})
    overrides_result = None
    try:
        overrides_result = await db.conversion_overrides.delete_many({"publisher_id": id_match})
    except Exception:
        pass

    # Whitelabel stats profiles and their tracked events.
    profiles = await db.stats_profiles.find({"publisher_id": id_match}, {"_id": 1, "slug": 1}).to_list(length=None)
    profile_clicks = 0
    profile_impressions = 0
    profile_conversions = 0
    manual_profile_rows = 0
    for profile in profiles:
        profile_id = profile.get("_id")
        profile_slug = profile.get("slug")
        profile_clicks += (await db.stats_profile_clicks.delete_many({"profile_id": profile_id})).deleted_count
        profile_impressions += (await db.stats_profile_impressions.delete_many({"profile_id": profile_id})).deleted_count
        profile_conversions += (await db.stats_profile_conversions.delete_many({"profile_id": profile_id})).deleted_count
        if profile_slug:
            manual_profile_rows += (await db.stats_profile_manual_conversions.delete_many({"profile_slug": profile_slug})).deleted_count
    profiles_result = await db.stats_profiles.delete_many({"publisher_id": id_match})

    # Reset the counters embedded on the surviving publisher document so the
    # publishers page cannot keep showing numbers whose rows were just deleted.
    await db.publishers.update_one(
        {"_id": _oid(publisher_id)},
        {"$set": {
            "total_clicks": 0, "valid_clicks": 0, "invalid_clicks": 0,
            "total_earnings": 0.0, "balance": 0.0,
        }},
    )

    return {
        "clicks_deleted": clicks_result.deleted_count,
        "withdrawals_deleted": withdrawals_result.deleted_count,
        "fraud_logs_deleted": fraud_result.deleted_count,
        "links_deleted": links_result.deleted_count,
        "link_events_deleted": events_result.deleted_count,
        "manual_conversions_deleted": (
            (manual_result.deleted_count if manual_result else 0)
            + (overrides_result.deleted_count if overrides_result else 0)
        ),
        "profiles_deleted": profiles_result.deleted_count,
        "profile_clicks_deleted": profile_clicks,
        "profile_impressions_deleted": profile_impressions,
        "profile_conversions_deleted": profile_conversions,
        "profile_manual_conversions_deleted": manual_profile_rows,
    }


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
