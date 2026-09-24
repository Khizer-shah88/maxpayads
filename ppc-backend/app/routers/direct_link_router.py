"""
Direct Link management — masked, hashed-slug affiliate URLs.

Link format:  https://<masked_domain>/#/<slug>
e.g.          https://click.example.com/#/a8f9z2

The slug is a cryptographically random 8-char base62 string.
When a user visits the URL, the frontend (/public route) reads the hash
fragment and calls POST /direct-links/conversions to record the event
and return the destination URL for redirection.

Collections:
  direct_links         — link definitions
  direct_link_events   — per-hit conversion records
"""
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from fastapi import APIRouter, Depends, Query, HTTPException, Request

from app.dependencies import get_db, get_current_admin
from app.core.exceptions import NotFoundError
from app.schemas.direct_link_schema import DirectLinkCreate, DirectLinkUpdate

router = APIRouter(prefix="/direct-links", tags=["Direct Links"])

_SLUG_CHARS = string.ascii_letters + string.digits  # base62
_SHARE_ID_LENGTH = 24  # unguessable secret for the public stats URL


# ─── helpers ──────────────────────────────────────────────────────────────────

def _oid(link_id: str) -> ObjectId:
    try:
        return ObjectId(link_id)
    except (InvalidId, TypeError):
        raise NotFoundError("Direct Link")


def _gen_slug(length: int = 8) -> str:
    """Generate a cryptographically random base62 slug."""
    return "".join(secrets.choice(_SLUG_CHARS) for _ in range(length))


def _gen_share_id(length: int = _SHARE_ID_LENGTH) -> str:
    """Generate a cryptographically random share ID for the public stats URL."""
    return "".join(secrets.choice(_SLUG_CHARS) for _ in range(length))


async def _unique_slug(db) -> str:
    for _ in range(10):
        slug = _gen_slug()
        if not await db.direct_links.find_one({"slug": slug}):
            return slug
    raise RuntimeError("Could not generate unique slug after 10 attempts")


def _masked_url(doc: dict) -> str:
    domain = doc.get("masked_domain", "")
    slug = doc.get("slug", "")
    if not domain:
        return ""
    return f"https://{domain}/#/{slug}"


async def _unique_share_id(db) -> str:
    """Generate a share ID that is not currently in use by any link."""
    for _ in range(10):
        share_id = _gen_share_id()
        if not await db.direct_links.find_one({"stats_share_id": share_id}):
            return share_id
    raise RuntimeError("Could not generate unique share ID after 10 attempts")


async def _ensure_publisher_stats_link(publisher_id: str, db) -> dict:
    """Resolve the same stats record for every publisher action, creating it if needed."""
    try:
        pub_oid = ObjectId(publisher_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid publisher ID")
    publisher = await db.publishers.find_one({"_id": pub_oid, "role": "publisher"})
    if not publisher:
        raise HTTPException(status_code=404, detail="Publisher not found")
    if publisher.get("status") in ("banned", "removed"):
        raise HTTPException(status_code=403, detail="Direct Link Stats unavailable: publisher is banned or removed")

    publisher_id = str(pub_oid)
    link = await db.direct_links.find_one(
        {"publisher_id": publisher_id, "status": {"$in": ["active", "paused"]}},
        sort=[("created_at", -1), ("_id", -1)],
    )
    if link:
        return link

    previous = await db.direct_links.find_one(
        {"publisher_id": publisher_id}, sort=[("created_at", -1), ("_id", -1)],
    ) or {}
    now = datetime.utcnow()
    # Manual/name-only publishers have no traffic link. Keep their report in a
    # paused, domain-free record so stats setup cannot create a redirect URL.
    # The existing unique slug index makes concurrent setup requests idempotent.
    query = {"slug": f"stats-{publisher_id}"}
    doc = {
        **query,
        "publisher_id": publisher_id,
        "publisher_name": publisher.get("name", ""),
        "name": f"{publisher.get('name', 'Publisher')} stats",
        "status": "paused",
        "stats_share_id": await _unique_share_id(db),
        "preferences": previous.get("preferences") or {},
        "stats_domain": previous.get("stats_domain") or "",
        "total_clicks": 0,
        "total_conversions": 0,
        "created_at": now,
        "updated_at": now,
    }
    try:
        link = await db.direct_links.find_one_and_update(
            query, {"$setOnInsert": doc}, upsert=True, return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        link = await db.direct_links.find_one(query)
        if not link:
            raise

    if link.get("status") == "archived":
        # Reopening stats must not revive an archived share URL.
        await db.direct_links.update_one(
            {"_id": link["_id"], "status": "archived"},
            {"$set": {"status": "paused", "stats_share_id": await _unique_share_id(db), "updated_at": now}},
        )
        link = await db.direct_links.find_one(query)
    return link


def _serialize(doc: dict, today_conversions: int = 0, manual_conversions: int = 0) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "publisher_id": doc.get("publisher_id", ""),
        "publisher_name": doc.get("publisher_name", ""),
        "campaign_id": doc.get("campaign_id"),
        "masked_domain": doc.get("masked_domain", ""),
        "slug": doc.get("slug", ""),
        "masked_url": _masked_url(doc),
        "destination_url": doc.get("destination_url", ""),
        "prelander_template_id": doc.get("prelander_template_id"),
        "status": doc.get("status", "active"),
        "notes": doc.get("notes"),
        "daily_conversion_cap": doc.get("daily_conversion_cap", 0),
        "preferences": doc.get("preferences") or {},
        "stats_share_id": doc.get("stats_share_id"),
        "stats_domain": doc.get("stats_domain") or "",
        "total_clicks": doc.get("total_clicks", 0),
        # Accurate total = tracked conversions on the link + any admin-entered
        # manual conversions for that link, so adding a conversion updates the
        # shown number in real time.
        "total_conversions": (doc.get("total_conversions", 0) or 0) + manual_conversions,
        "today_conversions": today_conversions,
        "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
        "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else None,
    }


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.post("/publisher/{publisher_id}/stats-link")
async def ensure_publisher_stats_link(
    publisher_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    link = await _ensure_publisher_stats_link(publisher_id, db)
    return {"success": True, "link": _serialize(link)}


@router.get("")
async def list_links(
    publisher_id: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    query: dict = {}
    if publisher_id:
        query["publisher_id"] = publisher_id
    if campaign_id:
        query["campaign_id"] = campaign_id
    if status:
        query["status"] = status

    cursor = db.direct_links.find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=500)

    # Batch today's conversions
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    link_ids = [str(d["_id"]) for d in docs]
    today_map: dict = {}
    if link_ids:
        pipeline = [
            {"$match": {"link_id": {"$in": link_ids}, "created_at": {"$gte": today_start}}},
            {"$group": {"_id": "$link_id", "count": {"$sum": 1}}},
        ]
        async for row in db.direct_link_events.aggregate(pipeline):
            today_map[row["_id"]] = row["count"]

    # Batch sum of admin-entered manual conversions per link (real-time total).
    manual_map: dict = {}
    if link_ids:
        mp = [
            {"$match": {"link_id": {"$in": link_ids}}},
            {"$group": {"_id": "$link_id", "count": {"$sum": "$conversions"}}},
        ]
        async for row in db.direct_link_manual_conversions.aggregate(mp):
            manual_map[row["_id"]] = row["count"] or 0

    return {
        "success": True,
        "links": [
            _serialize(
                d,
                today_map.get(str(d["_id"]), 0),
                manual_map.get(str(d["_id"]), 0),
            )
            for d in docs
        ],
        "total": len(docs),
    }


@router.post("/cleanup-duplicate-links", status_code=200)
async def cleanup_duplicate_links(
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    One-time cleanup: for each publisher, keep only the most recently created
    active/paused link and archive all older ones.
    """
    # Get all publishers that have more than one active/paused link
    pipeline = [
        {"$match": {"status": {"$in": ["active", "paused"]}}},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$publisher_id",
            "links": {"$push": {"id": "$_id", "created_at": "$created_at"}},
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
    ]
    results = await db.direct_links.aggregate(pipeline).to_list(length=None)

    total_archived = 0
    for pub in results:
        # links are sorted newest first — keep the first, archive the rest
        links_to_archive = pub["links"][1:]  # skip index 0 (newest)
        ids_to_archive = [l["id"] for l in links_to_archive]
        if ids_to_archive:
            result = await db.direct_links.update_many(
                {"_id": {"$in": ids_to_archive}},
                {"$set": {
                    "status": "archived",
                    "updated_at": datetime.utcnow(),
                    "archived_reason": "superseded_by_newer_link",
                }},
            )
            total_archived += result.modified_count

    return {
        "success": True,
        "publishers_affected": len(results),
        "links_archived": total_archived,
        "message": f"Archived {total_archived} duplicate links across {len(results)} publishers",
    }



@router.get("/conversions")
async def list_conversions(
    link_id: Optional[str] = Query(None),
    publisher_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Daily conversion log for all/specific direct links."""
    query: dict = {}
    if link_id:
        query["link_id"] = link_id
    if publisher_id:
        query["publisher_id"] = publisher_id

    from app.utils.date_utils import timestamp_range_query
    tr = timestamp_range_query(date_from, date_to)
    if tr:
        query["created_at"] = tr

    total = await db.direct_link_events.count_documents(query)
    skip = (page - 1) * limit
    cursor = db.direct_link_events.find(query).sort("created_at", -1).skip(skip).limit(limit)
    events = await cursor.to_list(length=None)

    for e in events:
        e["id"] = str(e.pop("_id"))
        if e.get("created_at"):
            e["created_at"] = e["created_at"].isoformat()

    return {
        "success": True,
        "conversions": events,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/conversions/daily-summary")
async def daily_conversion_summary(
    publisher_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Aggregate daily conversion counts — used by the tracking dashboard chart."""
    since = datetime.utcnow() - timedelta(days=days)
    match: dict = {"created_at": {"$gte": since}}
    if publisher_id:
        match["publisher_id"] = publisher_id

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "year": {"$year": "$created_at"},
                "month": {"$month": "$created_at"},
                "day": {"$dayOfMonth": "$created_at"},
            },
            "conversions": {"$sum": 1},
            "unique_links": {"$addToSet": "$link_id"},
        }},
        {"$sort": {"_id.year": 1, "_id.month": 1, "_id.day": 1}},
    ]
    results = await db.direct_link_events.aggregate(pipeline).to_list(length=None)
    summary = []
    for r in results:
        d = r["_id"]
        summary.append({
            "date": f"{d['year']}-{d['month']:02d}-{d['day']:02d}",
            "conversions": r["conversions"],
            "unique_links": len(r["unique_links"]),
        })
    return {"success": True, "summary": summary, "days": days}


@router.get("/{link_id}")
async def get_link(
    link_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    doc = await db.direct_links.find_one({"_id": _oid(link_id)})
    if not doc:
        raise NotFoundError("Direct Link")
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await db.direct_link_events.count_documents({
        "link_id": link_id, "created_at": {"$gte": today_start}
    })
    manual_count = 0
    mcursor = db.direct_link_manual_conversions.find({"link_id": link_id})
    async for m in mcursor:
        manual_count += int(m.get("conversions", 0) or 0)
    return {"success": True, "link": _serialize(doc, today_count, manual_count)}


@router.post("", status_code=201)
async def create_link(
    data: DirectLinkCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    slug = await _unique_slug(db)

    # Resolve publisher name for display
    pub_name = ""
    try:
        pub = await db.publishers.find_one({"_id": ObjectId(data.publisher_id)})
        if pub:
            pub_name = pub.get("name", "")
    except Exception:
        pass

    # ── Delete any existing links for this publisher ────────────────────────
    # Only one link per publisher — hard delete all previous ones
    # NOTE: This is now handled manually by admin via the delete button
    # We do NOT auto-delete here anymore

    now = datetime.utcnow()
    stats_share_id = await _unique_share_id(db)
    doc = {
        **data.model_dump(),
        "slug": slug,
        "stats_share_id": stats_share_id,
        "publisher_name": pub_name,
        "total_clicks": 0,
        "total_conversions": 0,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.direct_links.insert_one(doc)
    doc["_id"] = result.inserted_id
    return {
        "success": True,
        "link_id": str(result.inserted_id),
        "link": _serialize(doc),
        "message": "Direct link created",
    }


@router.put("/{link_id}")
async def update_link(
    link_id: str,
    data: DirectLinkUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    result = await db.direct_links.update_one(
        {"_id": _oid(link_id)}, {"$set": update_data}
    )
    if result.matched_count == 0:
        raise NotFoundError("Direct Link")
    doc = await db.direct_links.find_one({"_id": _oid(link_id)})
    return {"success": True, "link": _serialize(doc), "message": "Direct link updated"}


@router.post("/{link_id}/regenerate-slug")
async def regenerate_slug(
    link_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Generate a fresh slug for the link (old slug immediately stops working)."""
    doc = await db.direct_links.find_one({"_id": _oid(link_id)})
    if not doc:
        raise NotFoundError("Direct Link")
    new_slug = await _unique_slug(db)
    await db.direct_links.update_one(
        {"_id": _oid(link_id)},
        {"$set": {"slug": new_slug, "updated_at": datetime.utcnow()}},
    )
    doc["slug"] = new_slug
    return {"success": True, "link": _serialize(doc), "message": "Slug regenerated"}


@router.delete("/{link_id}")
async def delete_link(
    link_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    doc = await db.direct_links.find_one({"_id": _oid(link_id)})
    if not doc:
        raise NotFoundError("Direct Link")
    await db.direct_links.delete_one({"_id": _oid(link_id)})
    # Keep conversion events (audit trail) — just orphan them
    return {"success": True, "message": "Direct link deleted"}


# ─── Public conversion endpoint (no auth — called by the masked page) ─────────

@router.post("/conversions")
async def record_conversion(
    request: Request,
    data: dict,
    db=Depends(get_db),
):
    """
    Record a hit on a direct link with fraud validation and enriched tracking.
    Called by the masked landing page when the user arrives via a hash-slug URL.
    
    Tracks:
    - Unique clicks (first click from IP in time window)
    - Valid clicks (passed fraud detection)
    - Invalid clicks (failed fraud checks)
    - OS, device type, country
    - Fraud score

    Body: { "slug": "<8-char slug>", "metadata": {...} }
    """
    slug = (data.get("slug") or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")

    doc = await db.direct_links.find_one({"slug": slug, "status": "active"})
    if not doc:
        raise HTTPException(status_code=404, detail="Link not found or inactive")

    link_id = str(doc["_id"])
    publisher_id = doc.get("publisher_id", "")

    # Enforce daily cap if set
    cap = doc.get("daily_conversion_cap", 0)
    if cap and cap > 0:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = await db.direct_link_events.count_documents({
            "link_id": link_id, "created_at": {"$gte": today_start}
        })
        if today_count >= cap:
            raise HTTPException(status_code=429, detail="Daily conversion cap reached")

    # Extract client IP
    cf_ip = request.headers.get("cf-connecting-ip", "")
    xff = request.headers.get("x-forwarded-for", "")
    ip = cf_ip or (xff.split(",")[0].strip() if xff else "") or (
        request.client.host if request.client else "unknown"
    )
    
    user_agent = request.headers.get("user-agent", "")

    # ─── Parse device info (OS, device type, browser) ───
    from app.utils.ua_parser import parse_user_agent
    device_info = parse_user_agent(user_agent)
    
    # ─── Get country from IP ───
    from app.utils.geo_utils import lookup_ip
    country_code, country_name = lookup_ip(ip)
    
    # ─── Check if unique click (first from this IP in last 24h) ───
    yesterday = datetime.utcnow() - timedelta(days=1)
    previous_click = await db.direct_link_events.find_one({
        "ip_address": ip,
        "link_id": link_id,
        "created_at": {"$gte": yesterday}
    })
    is_unique = previous_click is None
    
    # ─── Run fraud detection (basic checks) ───
    is_valid = True
    is_fraud = False
    fraud_score = 0.0
    fraud_reason = None
    
    try:
        # Import fraud detection from click router
        from app.services import fraud_detection_service as fds
        
        # Basic validation checks
        headers_dict = dict(request.headers)
        
        # Check for bot/datacenter IPs
        if await fds.is_datacenter_ip(ip):
            is_valid = False
            is_fraud = True
            fraud_reason = "datacenter_ip"
            fraud_score = 1.0
        # Check for suspicious user agent
        elif not user_agent or len(user_agent) < 20:
            is_valid = False
            fraud_reason = "suspicious_ua"
            fraud_score = 0.8
        # Check rate limiting (too many clicks from same IP)
        elif not is_unique:
            # Additional check: count clicks in last hour
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_clicks = await db.direct_link_events.count_documents({
                "ip_address": ip,
                "created_at": {"$gte": one_hour_ago}
            })
            if recent_clicks >= 10:  # More than 10 clicks/hour = suspicious
                is_valid = False
                fraud_reason = "rate_limit"
                fraud_score = 0.7
    except Exception as e:
        # If fraud check fails, log but don't block
        import logging
        logging.warning(f"Direct link fraud check failed: {e}")
        # Default to valid if check fails
        pass

    event = {
        "link_id": link_id,
        "publisher_id": publisher_id,
        "slug": slug,
        "ip_address": ip,
        "user_agent": user_agent[:500],
        "referrer": request.headers.get("referer", ""),
        "metadata": data.get("metadata") or {},
        "created_at": datetime.utcnow(),
        # Enhanced tracking fields
        "is_unique": is_unique,
        "is_valid": is_valid,
        "is_fraud": is_fraud,
        "fraud_score": fraud_score,
        "fraud_reason": fraud_reason,
        "device_type": device_info.get("device_type", "unknown"),
        "os": device_info.get("os", "Unknown"),
        "browser": device_info.get("browser", "Unknown"),
        "country_code": country_code or "Unknown",
        "country_name": country_name or "Unknown",
    }
    await db.direct_link_events.insert_one(event)

    # Increment counters on the link document
    # Only count valid clicks in total
    inc_data = {"total_clicks": 1}
    if is_valid:
        inc_data["total_conversions"] = 1
    
    await db.direct_links.update_one(
        {"_id": doc["_id"]},
        {"$inc": inc_data},
    )

    return {
        "success": True,
        "destination_url": doc.get("destination_url", ""),
        "prelander_template_id": doc.get("prelander_template_id"),
        # Return validation status for debugging (optional)
        "is_valid": is_valid,
        "is_unique": is_unique,
    }


# ─── Manual Conversion Override Endpoints ────────────────────────────────────

@router.post("/conversions/manual-override")
async def create_manual_conversion_override(
    data: dict,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Create or update manual conversion override for a specific date and publisher.
    
    Body: {
        "date": "2024-01-15",
        "publisher_id": "...",
        "link_id": "..." (optional),
        "manual_conversions": 50,
        "reason": "Manual adjustment due to tracking issues"
    }
    """
    required_fields = ["date", "publisher_id", "manual_conversions", "reason"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"{field} is required")
    
    date_str = data["date"]
    publisher_id = data["publisher_id"]
    link_id = data.get("link_id")
    manual_conversions = data["manual_conversions"]
    reason = data["reason"].strip()
    
    if manual_conversions < 0:
        raise HTTPException(status_code=400, detail="Manual conversions must be non-negative")
    
    if not reason:
        raise HTTPException(status_code=400, detail="Reason cannot be empty")
    
    # Parse and validate date
    try:
        from datetime import datetime
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        date_start = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_obj.replace(hour=23, minute=59, second=59, microsecond=999999)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    # Verify publisher exists
    try:
        pub_oid = ObjectId(publisher_id)
        publisher = await db.publishers.find_one({"_id": pub_oid, "role": "publisher"})
        if not publisher:
            raise HTTPException(status_code=404, detail="Publisher not found")
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid publisher ID")
    
    # Get raw clicks for the date to calculate CR.
    # Clicks are written by redirect_pipeline.stage_record_click, which stores
    # `timestamp` (not `created_at`) and `is_valid` (not `is_fraud`), and never
    # carries a `direct_link_id` — so the filter uses the fields clicks
    # actually have, and a link_id (when given) cannot narrow the count.
    click_query = {
        "publisher_id": publisher_id,
        "timestamp": {"$gte": date_start, "$lte": date_end},
        "is_valid": True
    }

    raw_clicks = await db.clicks.count_documents(click_query)
    calculated_cr = (manual_conversions / raw_clicks * 100) if raw_clicks > 0 else 0
    
    # Create or update override record
    override_query = {
        "date": date_str,
        "publisher_id": publisher_id
    }
    if link_id:
        override_query["link_id"] = link_id
    
    override_data = {
        **override_query,
        "raw_clicks": raw_clicks,
        "manual_conversions": manual_conversions,
        "calculated_cr": calculated_cr,
        "reason": reason,
        "is_manual_override": True,
        "override_updated_by": str(current_user["id"]),
        "override_updated_at": datetime.utcnow(),
    }
    
    # Upsert the override
    result = await db.conversion_overrides.update_one(
        override_query,
        {"$set": override_data},
        upsert=True
    )
    
    action = "updated" if result.matched_count > 0 else "created"
    
    return {
        "success": True,
        "message": f"Manual conversion override {action}",
        "data": {
            "date": date_str,
            "publisher_id": publisher_id,
            "link_id": link_id,
            "raw_clicks": raw_clicks,
            "manual_conversions": manual_conversions,
            "calculated_cr": round(calculated_cr, 2),
            "reason": reason
        }
    }


@router.get("/conversions/overrides")
async def get_conversion_overrides(
    publisher_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get manual conversion overrides with optional filtering."""
    query = {"is_manual_override": True}
    
    if publisher_id:
        query["publisher_id"] = publisher_id
    
    # Date range filter
    if date_from or date_to:
        date_filter = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to
        query["date"] = date_filter
    
    cursor = db.conversion_overrides.find(query).sort("date", -1)
    overrides = await cursor.to_list(length=1000)
    
    # Clean up for response
    for override in overrides:
        override["id"] = str(override.pop("_id"))
        if override.get("override_updated_at"):
            override["override_updated_at"] = override["override_updated_at"].isoformat()
    
    return {
        "success": True,
        "overrides": overrides,
        "total": len(overrides)
    }


@router.delete("/conversions/overrides/{override_id}")
async def delete_conversion_override(
    override_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Delete a manual conversion override."""
    try:
        oid = ObjectId(override_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid override ID")
    
    result = await db.conversion_overrides.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Override not found")
    
    return {
        "success": True,
        "message": "Conversion override deleted"
    }


# ─── White-Label Stats Link (share ID based) ─────────────────────────────────

async def _build_stats_url(request: Request, db, share_id: str, link: Optional[dict] = None) -> str:
    """Build the public stats URL for a share ID using the configured domain."""
    # Default: current admin panel origin — always works regardless of hosting.
    forwarded_proto = request.headers.get("x-forwarded-proto", "https")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    if forwarded_host:
        base_url = f"{forwarded_proto}://{forwarded_host}"
    else:
        base_url = str(request.base_url).rstrip("/")

    # PER-PUBLISHER white-label domain wins (Admin → Direct Link Stats →
    # per-publisher domain assignment, e.g. fisherhub.com for one pub only).
    link_domain = ((link or {}).get("stats_domain") or "").strip().rstrip("/")
    if link_domain:
        if not link_domain.startswith("http"):
            link_domain = f"https://{link_domain}"
        return f"{link_domain}/public-stats/{share_id}"

    # Optional GLOBAL custom white-label stats domain (Admin → Settings).
    stats_domain_doc = await db.system_settings.find_one({"key": "stats_domain"})
    if stats_domain_doc and stats_domain_doc.get("value", "").strip():
        custom_domain = stats_domain_doc["value"].strip().rstrip("/")
        if not custom_domain.startswith("http"):
            custom_domain = f"https://{custom_domain}"
        base_url = custom_domain

    return f"{base_url}/public-stats/{share_id}"


@router.post("/{link_id}/share-stats-link")
async def share_stats_link(
    link_id: str,
    request: Request,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Build the shareable white-label stats URL for a link.
    The underlying share ID stays the same — this only returns the URL.
    """
    doc = await db.direct_links.find_one({"_id": _oid(link_id)})
    if not doc:
        raise NotFoundError("Direct Link")

    # Ensure a share ID exists (older links may pre-date the field)
    share_id = doc.get("stats_share_id")
    if not share_id:
        share_id = await _unique_share_id(db)
        await db.direct_links.update_one(
            {"_id": doc["_id"]},
            {"$set": {"stats_share_id": share_id, "updated_at": datetime.utcnow()}},
        )

    stats_url = await _build_stats_url(request, db, share_id, link=doc)
    return {
        "success": True,
        "stats_url": stats_url,
        "share_id": share_id,
        "link_id": str(doc["_id"]),
    }


@router.post("/{link_id}/regenerate-stats-link")
async def regenerate_stats_link(
    link_id: str,
    request: Request,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Regenerate the public statistics URL for a link.

    - Generates a brand-new share ID → the old URL expires immediately.
    - Report configuration (preferences) is untouched.
    - All conversion / click data is untouched.

    Anyone opening the old link afterwards sees only
    "This statistics link has expired." with no further information.
    """
    doc = await db.direct_links.find_one({"_id": _oid(link_id)})
    if not doc:
        raise NotFoundError("Direct Link")

    old_share_id = doc.get("stats_share_id")
    new_share_id = await _unique_share_id(db)

    # Make sure the new ID can never collide with the old one
    while new_share_id == old_share_id:
        new_share_id = await _unique_share_id(db)

    await db.direct_links.update_one(
        {"_id": doc["_id"]},
        {"$set": {
            "stats_share_id": new_share_id,
            "updated_at": datetime.utcnow(),
        }},
    )

    stats_url = await _build_stats_url(request, db, new_share_id, link=doc)
    return {
        "success": True,
        "stats_url": stats_url,
        "share_id": new_share_id,
        "link_id": str(doc["_id"]),
        "message": "Statistics link regenerated — the previous link has expired",
    }


@router.post("/generate-stats-token")
async def generate_stats_token(
    request: Request,
    data: dict,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Legacy-compatible entry point: return the publisher's shareable stats URL,
    initializing a stats record when they have no active/paused direct link.

    Body: { "publisher_id": "..." }
    """
    publisher_id = data.get("publisher_id")
    if not publisher_id:
        raise HTTPException(status_code=400, detail="publisher_id is required")

    link = await _ensure_publisher_stats_link(publisher_id, db)

    share_id = link.get("stats_share_id")
    if not share_id:
        share_id = await _unique_share_id(db)
        await db.direct_links.update_one(
            {"_id": link["_id"]},
            {"$set": {"stats_share_id": share_id, "updated_at": datetime.utcnow()}},
        )

    stats_url = await _build_stats_url(request, db, share_id, link=link)

    return {
        "success": True,
        "share_id": share_id,
        "stats_url": stats_url,
        "publisher_name": link.get("publisher_name", "Unknown"),
        "expires": None,
    }
