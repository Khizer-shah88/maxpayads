
from fastapi import APIRouter, Request, Query, Depends
from fastapi.responses import HTMLResponse
from typing import Optional
from bson import ObjectId
from app.dependencies import get_db, get_redis_client, get_current_admin
from app.utils.date_utils import timestamp_range_query
from app.services.redirect_pipeline import context_from_request, resolve_redirect
from app.routing_engine.redirect_manager import build_redirect
import logging

router = APIRouter(tags=["Click Tracking"])
logger = logging.getLogger(__name__)


# Neutral 403 screen for signature failures — deliberately identical in shape
# to the prelander denied page (no reason, no ids, no link structure hints).
_INVALID_LINK_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Invalid Link</title>
<style>
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:#f0f2f5; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
  .box {{ text-align:center; max-width:380px; padding:0 20px; }}
  .icon {{ width:64px; height:64px; border-radius:50%; background:#e5e7eb; margin:0 auto 16px;
           display:flex; align-items:center; justify-content:center; }}
  h1 {{ font-size:18px; color:#374151; margin:0 0 8px; font-weight:600; }}
  p {{ color:#6b7280; font-size:14px; margin:0; }}
</style>
</head>
<body>
  <div class="box">
    <div class="icon">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="2">
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <h1>Invalid or expired link</h1>
    <p>This link is not valid. Please contact your account manager for a fresh link.</p>
  </div>
</body>
</html>"""


def _invalid_link_response() -> HTMLResponse:
    """403 error state for failed Smartlink signature validation (spec)."""
    return HTMLResponse(content=_INVALID_LINK_PAGE, status_code=403)


@router.get("/click")
async def track_click(
    request: Request,
    # NOTE: pub and site are now OPTIONAL — we parse dynamically from structures
    pub: Optional[str] = Query(None, description="Publisher ID (legacy parameter, auto-detected)"),
    site: Optional[str] = Query(None, description="Website ID (legacy parameter, auto-detected)"),
    # Alternative structure parameters (will be auto-detected)
    tag: Optional[str] = Query(None, description="Publisher ID (alternative parameter)"),
    sid: Optional[str] = Query(None, description="Website ID (alternative parameter)"),
    hmac_token: Optional[str] = Query(None, alias="hmac", description="System-generated link signature (Smartlink signing)"),
    nonce: Optional[str] = Query(None, alias="n", description="Per-link nonce folded into the signature"),
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

    Dynamically supports multiple smartlink structures:
    - Standard: ?pub={PUB}&site={SITE}
    - Tag + SID: ?tag={PUB}&sid={SITE}
    - Tag Only: ?tag={PUB}
    - Custom structures defined in admin panel

    LEGACY SMARTLINK SIGNING: previously issued links carry `hmac=<hex>` — an
    HMAC-SHA256 bound to the exact pub/site Tag IDs. A supplied token is ALWAYS
    verified server-side: any modified character, arbitrary value, or a token
    moved to different parameters → 403 invalid-link screen. Strict mode
    (SMARTLINK_HASH_REQUIRED=true) rejects unsigned links and must remain off
    for the standard pub/site-only link format.
    """
    # ── Dynamic structure parsing ─────────────────────────────────────────
    # Parse the request using registered smartlink structures
    from app.services.smartlink_parser import parse_smartlink_from_request
    
    pub_value, site_value, structure_name = await parse_smartlink_from_request(request, db)
    
    if not pub_value:
        logger.warning(
            "[/click] No valid smartlink parameters found ip=%s params=%s",
            request.client.host if request.client else "unknown",
            dict(request.query_params),
        )
        return _invalid_link_response()
    
    logger.info(
        f"[/click] Parsed smartlink: structure='{structure_name}' pub={pub_value[:12]}... site={site_value[:12] if site_value else 'N/A'}..."
    )
    
    # ── Link-signature validation (tamper prevention) ─────────────────────
    # Runs before anything else: a forged/tampered link must never reach the
    # pipeline (no click row, no routing, no prelander session).
    from app.services import smartlink_signing as sls
    if hmac_token or sls.hash_required():
        if not sls.verify_link_token(pub_value, site_value, hmac_token or "", nonce or ""):
            logger.warning(
                "[/click] Smartlink signature REJECTED (tampered/invalid/missing) pub=%s… ip=%s",
                (pub_value or "")[:12],
                request.client.host if request.client else "unknown",
            )
            return _invalid_link_response()
    try:
        ctx = context_from_request(request, pub_value, site_value)
        await resolve_redirect(ctx, db, redis)
        # A document navigation from the Anchor distinguishes a legitimate
        # entry from pasting an Inter URL, even when /click was typed directly.
        managed_hop = "/d/h_" in ctx.destination_url or "/_auth/" in ctx.destination_url
        response = build_redirect(ctx.destination_url, ctx.referrer_suppression or managed_hop)
    except Exception:
        # The visitor must ALWAYS leave with a URL — a bare JSON 500 on the
        # publisher's page is a dead flow. Log the real cause server-side and
        # send the visitor to the global fallback instead.
        logger.exception("[/click] Pipeline failed — serving fallback redirect")
        from app.services.redirect_pipeline import FALLBACK_URL as _pipeline_fallback
        from fastapi.responses import RedirectResponse
        response = RedirectResponse(url=_pipeline_fallback, status_code=302)

    # Authorization cookie — a signed reference to this click's prelander
    # session (created by stage_authorize_prelander during resolve_redirect).
    # The reference names the high-entropy random session token; internal
    # ids (click/campaign/offer/publisher) never leave the server. HttpOnly +
    # SameSite=Lax: readable by no script, never sent on cross-site requests.
    # Cross-domain hops rely on the server-side fingerprint/slug binding
    # instead (prelander_auth_service.validate_authorization) — the cookie is
    # the convenient factor when the prelander runs on this same domain.
    try:
        from app.services import prelander_auth_service as pas
        from app.utils.ip_utils import get_client_ip

        if ctx.prelander_auth_token:
            ip = get_client_ip(ctx.headers, ctx.ip or "0.0.0.0")
            reference = pas.session_reference(ctx.prelander_auth_token, ip, ctx.user_agent or "")
            if reference:
                response.set_cookie(
                    key=pas.COOKIE_NAME,
                    value=reference,
                    max_age=pas.cookie_ttl_seconds(),
                    **pas.cookie_flags(),
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
