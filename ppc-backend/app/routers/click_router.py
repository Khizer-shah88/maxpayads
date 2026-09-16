
from fastapi import APIRouter, Request, Query, Depends
from typing import Optional
from bson import ObjectId
from app.dependencies import get_db, get_redis_client, get_current_admin
from app.utils.date_utils import timestamp_range_query
from app.services.redirect_pipeline import context_from_request, resolve_redirect
from app.routing_engine.redirect_manager import build_redirect
import logging

router = APIRouter(tags=["Click Tracking"])
logger = logging.getLogger(__name__)


@router.get("/click")
async def track_click(
    request: Request,
    pub: str = Query(..., description="Publisher ID (ObjectId or public_id PUB_XXXXXXXX)"),
    site: Optional[str] = Query(None, description="Website ID (ObjectId or public_id SITE_XXXXXXXX)"),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    """
    Smartlink entry point — the visitor's first hop into the network.

    Everything this endpoint does happens in the redirect pipeline
    (`app.services.redirect_pipeline`), which runs the stages in order and
    records each decision on a single RedirectResolutionContext:

        identify_publisher → detect_visitor → screen_traffic → record_click
        → resolve_chain → resolve_campaign → evaluate_offer → decide_prelander
        → resolve_cpc → deliver

    The endpoint itself only turns the resolved context into a response, so the
    flow stays in one traceable place rather than spread across the handler.

    Backward compatible: accepts ?pub=ObjectId&site=ObjectId as well as
    ?pub=PUB_XXXXXXXX&site=SITE_XXXXXXXX.
    """
    ctx = context_from_request(request, pub, site)
    await resolve_redirect(ctx, db, redis)
    response = build_redirect(ctx.destination_url, ctx.referrer_suppression)

    # Authorization cookie — a signed reference to this click's prelander
    # session (created by stage_authorize_prelander during resolve_redirect).
    # HttpOnly + SameSite=Lax: readable by no script, never sent on
    # cross-site subresource requests. Cross-domain hops rely on the
    # server-side fingerprint/slug binding instead (see
    # prelander_auth_service.validate_authorization) — the cookie is the
    # convenient factor when the prelander runs on this same domain.
    try:
        from app.services import prelander_auth_service as pas
        from app.utils.ip_utils import get_client_ip

        if ctx.click_id and "/d/" in (ctx.destination_url or ""):
            ip = get_client_ip(ctx.headers, ctx.ip or "0.0.0.0")
            reference = pas.session_reference(ctx.click_id, ip, ctx.user_agent or "")
            if reference:
                response.set_cookie(
                    key=pas.COOKIE_NAME,
                    value=reference,
                    max_age=pas.COOKIE_TTL_SECONDS,
                    httponly=True,
                    samesite="lax",
                    secure=True,
                )
    except Exception:
        # The cookie is an optional factor — never let it break the redirect.
        pass

    return response


@router.get("/clicks/{click_id}/trace")
async def get_click_trace(
    click_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Explain one click (admin only).

    Returns the stage-by-stage resolution trace the redirect pipeline recorded —
    what each stage decided and why this visitor ended up at this URL. Empty when
    REDIRECT_TRACE_ENABLED is off, or for clicks recorded before tracing existed.
    """
    try:
        oid = ObjectId(click_id)
    except Exception:
        return {"success": False, "message": "Invalid click id"}

    click = await db.clicks.find_one(
        {"_id": oid},
        {
            "resolution_trace": 1, "destination_url": 1, "publisher_id": 1,
            "website_id": 1, "campaign_id": 1, "status": 1, "os": 1,
            "country_code": 1, "cpc": 1, "earnings": 1, "timestamp": 1,
        },
    )
    if not click:
        return {"success": False, "message": "Click not found"}

    timestamp = click.get("timestamp")
    return {
        "success": True,
        "click": {
            "id": click_id,
            "publisher_id": click.get("publisher_id"),
            "website_id": click.get("website_id"),
            "campaign_id": click.get("campaign_id"),
            "status": click.get("status"),
            "os": click.get("os"),
            "country_code": click.get("country_code"),
            "destination_url": click.get("destination_url"),
            "cpc": click.get("cpc"),
            "earnings": click.get("earnings"),
            "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
        },
        "trace": click.get("resolution_trace") or [],
    }


@router.get("/clicks")
async def get_clicks(
    publisher_id: Optional[str] = Query(None),
    website_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    country_code: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    os: Optional[str] = Query(None),
    browser: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get all clicks with filters (admin only)."""
    query = {}
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

    skip = (page - 1) * limit
    total = await db.clicks.count_documents(query)
    cursor = db.clicks.find(query).skip(skip).limit(limit).sort("timestamp", -1)
    clicks = await cursor.to_list(length=None)

    # Collect unique website_ids to resolve domains
    website_ids = set()
    for c in clicks:
        if c.get("website_id"):
            try:
                website_ids.add(c["website_id"])
            except Exception:
                pass

    # Build website_id -> domain lookup
    website_domains = {}
    if website_ids:
        obj_ids = []
        for wid in website_ids:
            try:
                obj_ids.append(ObjectId(wid))
            except Exception:
                pass
        if obj_ids:
            wcursor = db.websites.find({"_id": {"$in": obj_ids}}, {"domain": 1})
            async for w in wcursor:
                website_domains[str(w["_id"])] = w.get("domain", "")

    for c in clicks:
        c["id"] = str(c.pop("_id"))
        if c.get("website_id") and c["website_id"] in website_domains:
            c["website_domain"] = website_domains[c["website_id"]]
        if "timestamp" in c:
            c["timestamp"] = c["timestamp"].isoformat()
        if "processed_at" in c and c["processed_at"]:
            c["processed_at"] = c["processed_at"].isoformat()

    return {
        "success": True,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "clicks": clicks,
    }


@router.get("/clicks/export-csv")
async def export_clicks_csv(
    publisher_id: Optional[str] = Query(None),
    website_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    country_code: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    os: Optional[str] = Query(None),
    browser: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Export click data as CSV with same filters as stats page."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    query = {}
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

    cursor = db.clicks.find(query).sort("timestamp", -1).limit(50000)
    clicks = await cursor.to_list(length=None)

    # Resolve website domains
    website_ids = set()
    for c in clicks:
        if c.get("website_id"):
            website_ids.add(c["website_id"])
    website_domains = {}
    if website_ids:
        obj_ids = []
        for wid in website_ids:
            try:
                obj_ids.append(ObjectId(wid))
            except Exception:
                pass
        if obj_ids:
            wcursor = db.websites.find({"_id": {"$in": obj_ids}}, {"domain": 1})
            async for w in wcursor:
                website_domains[str(w["_id"])] = w.get("domain", "")

    output = io.StringIO()
    fieldnames = [
        "id", "publisher_id", "website", "referrer", "ip_address",
        "country_code", "country_name", "device_type", "os", "browser",
        "status", "cpc", "earnings", "fraud_reason", "fraud_score", "timestamp"
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for c in clicks:
        wid = c.get("website_id", "")
        domain = website_domains.get(wid, wid) if wid else ""
        writer.writerow({
            "id": str(c.get("_id", "")),
            "publisher_id": c.get("publisher_id", ""),
            "website": domain,
            "referrer": c.get("referrer", ""),
            "ip_address": c.get("ip_address", ""),
            "country_code": c.get("country_code", ""),
            "country_name": c.get("country_name", ""),
            "device_type": c.get("device_type", ""),
            "os": c.get("os", ""),
            "browser": c.get("browser", ""),
            "status": c.get("status", ""),
            "cpc": c.get("cpc", 0),
            "earnings": c.get("earnings", 0),
            "fraud_reason": c.get("fraud_reason", ""),
            "fraud_score": c.get("fraud_score", 0),
            "timestamp": str(c.get("timestamp", "")),
        })

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=clicks.csv"},
    )
