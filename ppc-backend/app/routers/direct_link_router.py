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
from fastapi import APIRouter, Depends, Query, HTTPException, Request

from app.dependencies import get_db, get_current_admin
from app.core.exceptions import NotFoundError
from app.schemas.direct_link_schema import DirectLinkCreate, DirectLinkUpdate

router = APIRouter(prefix="/direct-links", tags=["Direct Links"])

_SLUG_CHARS = string.ascii_letters + string.digits  # base62


# ─── helpers ──────────────────────────────────────────────────────────────────

def _oid(link_id: str) -> ObjectId:
    try:
        return ObjectId(link_id)
    except (InvalidId, TypeError):
        raise NotFoundError("Direct Link")


def _gen_slug(length: int = 8) -> str:
    """Generate a cryptographically random base62 slug."""
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


def _serialize(doc: dict, today_conversions: int = 0) -> dict:
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
        "total_clicks": doc.get("total_clicks", 0),
        "total_conversions": doc.get("total_conversions", 0),
        "today_conversions": today_conversions,
        "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
        "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else None,
    }


# ─── CRUD ─────────────────────────────────────────────────────────────────────

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

    return {
        "success": True,
        "links": [_serialize(d, today_map.get(str(d["_id"]), 0)) for d in docs],
        "total": len(docs),
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
    return {"success": True, "link": _serialize(doc, today_count)}


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

    now = datetime.utcnow()
    doc = {
        **data.model_dump(),
        "slug": slug,
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
    Record a hit on a direct link.  Called by the masked landing page when
    the user arrives via a hash-slug URL.  Returns the destination URL.

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

    event = {
        "link_id": link_id,
        "publisher_id": publisher_id,
        "slug": slug,
        "ip_address": ip,
        "user_agent": request.headers.get("user-agent", "")[:500],
        "referrer": request.headers.get("referer", ""),
        "metadata": data.get("metadata") or {},
        "created_at": datetime.utcnow(),
    }
    await db.direct_link_events.insert_one(event)

    # Increment counters on the link document
    await db.direct_links.update_one(
        {"_id": doc["_id"]},
        {"$inc": {"total_clicks": 1, "total_conversions": 1}},
    )

    return {
        "success": True,
        "destination_url": doc.get("destination_url", ""),
        "prelander_template_id": doc.get("prelander_template_id"),
    }
