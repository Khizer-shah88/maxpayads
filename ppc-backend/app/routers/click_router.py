
from fastapi import APIRouter, Request, Query, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from datetime import datetime, timedelta
from typing import Optional
from bson import ObjectId
from app.dependencies import get_db, get_redis_client, get_current_admin
from app.utils.ip_utils import get_client_ip, is_datacenter_ip
from app.utils.ua_parser import parse_user_agent, is_bot_user_agent
from app.utils.date_utils import timestamp_range_query
from app.services.traffic_router import route_click
from app.routing_engine.redirect_manager import build_redirect
from app.core.constants import (
    MAX_CLICKS_PER_IP_PER_MINUTE,
    REDIS_CLICK_RATE_PREFIX,
    REDIS_DUPLICATE_CLICK_PREFIX,
    DUPLICATE_CLICK_WINDOW_SECONDS,
)
import logging

router = APIRouter(tags=["Click Tracking"])
logger = logging.getLogger(__name__)

FALLBACK_URL = "https://example.com"


async def _comprehensive_fraud_check(
    ip: str, 
    user_agent: str, 
    headers: dict,
    publisher_id: str,
    campaign_id: Optional[str],
    referer: str,
    db,
    redis,
    website_id: str = None
) -> tuple:
    """
    Comprehensive fraud check using new fraud detection service.
    Returns (block, soft_flag, reason, fraud_score, classification).
      - block=True: invalid/bot traffic → redirect to fallback
      - soft_flag=True: suspicious/duplicate → flag but still route
    """
    from app.services import fraud_detection_service as fds
    
    # Legacy checks for backward compatibility
    # Check 1: Bot user agent (legacy) — HARD BLOCK
    if is_bot_user_agent(user_agent):
        return True, False, "bot_user_agent", 1.0, fds.TRAFFIC_BOT

    # Check 2: Datacenter IP (legacy) — HARD BLOCK  
    if is_datacenter_ip(ip):
        return True, False, "datacenter_ip", 0.95, fds.TRAFFIC_INVALID

    # Check 3: Rate limit (legacy) — HARD BLOCK
    try:
        key = f"{REDIS_CLICK_RATE_PREFIX}{ip}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        if count > MAX_CLICKS_PER_IP_PER_MINUTE:
            return True, False, "rate_limit_exceeded", 0.90, fds.TRAFFIC_INVALID
    except Exception as e:
        logger.warning(f"Redis rate limit check failed: {e}")

    # Check 4: Duplicate IP+Website — SOFT FLAG
    try:
        site_suffix = f":{website_id}" if website_id else ""
        dup_key = f"{REDIS_DUPLICATE_CLICK_PREFIX}{ip}{site_suffix}"
        exists = await redis.exists(dup_key)
        if exists:
            return False, True, "duplicate_ip", 0.85, fds.TRAFFIC_DUPLICATE
        await redis.setex(dup_key, DUPLICATE_CLICK_WINDOW_SECONDS, "1")
    except Exception as e:
        logger.warning(f"Redis duplicate check failed: {e}")

    # NEW: Comprehensive fraud detection
    try:
        request_data = {
            "ip_address": ip,
            "user_agent": user_agent,
            "headers": headers,
            "publisher_id": publisher_id,
            "campaign_id": campaign_id,
            "referer": referer,
        }
        
        result = await fds.classify_traffic(db, redis, request_data)
        
        classification = result["classification"]
        fraud_score = result["score"] / 100.0  # Normalize to 0-1
        reasons = result["reasons"]
        should_reject = result["should_reject"]
        should_flag = result["should_flag"]
        
        # Join reasons for single fraud_reason field
        fraud_reason = "; ".join(reasons[:3]) if reasons else None
        
        # Decision logic
        if should_reject:
            # Invalid or bot traffic - hard block
            return True, False, fraud_reason, fraud_score, classification
        elif should_flag:
            # Suspicious or duplicate - soft flag
            return False, True, fraud_reason, fraud_score, classification
        else:
            # Valid traffic
            return False, False, None, fraud_score, classification
            
    except Exception as e:
        logger.error(f"Fraud detection service error: {e}")
        # Fallback to safe default on error
        return False, False, None, 0.0, fds.TRAFFIC_VALID


@router.get("/click")
async def track_click(
    request: Request,
    pub: str = Query(..., description="Publisher ID (ObjectId or public_id PUB_XXXXXXXX)"),
    site: Optional[str] = Query(None, description="Website ID (ObjectId or public_id SITE_XXXXXXXX)"),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
):
    """
    Main click tracking endpoint — exact flow:
    1. Click received → extract metadata
    2. Resolve publisher/website IDs (supports public_id or ObjectId)
    3. Fraud check (inline, fast rule-based)
    4. Campaign match
    5. GEO rules
    6. Device / OS rules
    7. Landing page (if set)
    8. Final redirect
    Target response time: < 50ms
    
    Backward Compatible:
    - Accepts old format: ?pub=ObjectId&site=ObjectId
    - Accepts new format: ?pub=PUB_XXXXXXXX&site=SITE_XXXXXXXX
    """
    start_time = datetime.utcnow()

    # --- Step 1: Resolve publisher and website IDs (backward compatible) ---
    from app.utils.public_id_utils import resolve_publisher_id, resolve_website_id
    
    publisher_id = await resolve_publisher_id(db, pub.strip())
    if not publisher_id:
        logger.warning(f"Invalid publisher identifier: {pub}")
        return build_redirect(FALLBACK_URL)
    
    website_id = None
    if site:
        site = site.strip().rstrip("/")
        website_id = await resolve_website_id(db, site)
        # If website_id not found, continue without it (backward compat)
        if not website_id:
            logger.warning(f"Website not found: {site}, continuing without website binding")
    
    # --- Step 2: Extract request metadata ---
    client_ip = get_client_ip(
        dict(request.headers),
        request.client.host if request.client else "0.0.0.0",
    )
    user_agent = request.headers.get("user-agent", "")
    # Referrer: check header first, fall back to ?ref= query param (passed by anchor domain)
    referrer = request.headers.get("referer", "") or request.query_params.get("ref", "")

    device_info = parse_user_agent(user_agent)
    from app.utils.geo_utils import lookup_ip
    country_code, country_name = lookup_ip(client_ip)

    # --- Step 3: Comprehensive fraud check (includes legacy + new detection) ---
    # Prepare headers dict for fraud detection
    headers_dict = dict(request.headers)
    
    is_blocked, is_flagged, fraud_reason, fraud_score, traffic_classification = await _comprehensive_fraud_check(
        client_ip, user_agent, headers_dict, publisher_id, None, referrer, db, redis, website_id=website_id
    )

    # Determine click status based on fraud check results
    if is_blocked:
        click_status = "invalid"
    elif is_flagged:
        click_status = "invalid"  # Flagged traffic is also marked invalid but still routes
    else:
        click_status = "pending"  # Will be validated by background task

    # Build click document (always use internal _id for storage)
    click_data = {
        "publisher_id": publisher_id,
        "website_id": website_id,
        "ip_address": client_ip,
        "country_code": country_code,
        "country_name": country_name,
        "device_type": device_info["device_type"],
        "os": device_info["os"],
        "browser": device_info["browser"],
        "user_agent": user_agent[:500],
        "referrer": referrer[:500] if referrer else None,
        "status": click_status,
        "is_valid": False,
        "fraud_reason": fraud_reason,
        "fraud_score": fraud_score,
        "traffic_classification": traffic_classification,  # NEW: Store classification
        "cpc": 0.0,
        "earnings": 0.0,
        "processed": is_blocked or is_flagged,
        "timestamp": start_time,
    }

    # --- Insert click to DB ---
    try:
        result = await db.clicks.insert_one(click_data.copy())
        click_id = str(result.inserted_id)
    except Exception as e:
        logger.error(f"Failed to insert click: {e}")
        return build_redirect(FALLBACK_URL)

    # HARD BLOCK: bot/datacenter/rate_limit → log fraud, redirect to fallback
    if is_blocked:
        try:
            from app.services.fraud_service import log_fraud
            from app.services.earnings_service import update_publisher_invalid_click, update_website_stats
            from app.services import fraud_detection_service as fds
            
            # Log security event
            await fds.log_security_event(
                db,
                event_type="fraud_detected",
                severity="warning",
                description=f"Blocked traffic: {fraud_reason}",
                metadata={
                    "click_id": click_id,
                    "ip": client_ip,
                    "classification": traffic_classification,
                    "fraud_score": fraud_score,
                }
            )
            
            await log_fraud(click_id, click_data, fraud_reason, fraud_score, db)
            await update_publisher_invalid_click(pub, db)
            if site:
                await update_website_stats(site, 0.0, False, db)
        except Exception as e:
            logger.warning(f"Failed to log inline fraud: {e}")
        return build_redirect(FALLBACK_URL)

    # SOFT FLAG (suspicious/duplicate): log as invalid but still route to the real offer
    if is_flagged:
        try:
            from app.services.fraud_service import log_fraud
            from app.services.earnings_service import update_publisher_invalid_click, update_website_stats
            from app.services import fraud_detection_service as fds
            
            # Log security event (lower severity for flags)
            await fds.log_security_event(
                db,
                event_type="suspicious_traffic",
                severity="info",
                description=f"Flagged traffic: {fraud_reason}",
                metadata={
                    "click_id": click_id,
                    "ip": client_ip,
                    "classification": traffic_classification,
                    "fraud_score": fraud_score,
                }
            )
            
            await log_fraud(click_id, click_data, fraud_reason, fraud_score, db)
            await update_publisher_invalid_click(publisher_id, db)
            if website_id:
                await update_website_stats(website_id, 0.0, False, db)
        except Exception as e:
            logger.warning(f"Failed to log flagged click: {e}")
        # Don't return here — continue to route to the real offer below

    # --- Step 4-8: Route click (publisher → campaign → GEO → device → lander → offer) ---
    destination = FALLBACK_URL
    referrer_suppression = False
    try:
        destination, referrer_suppression = await route_click(click_data, db, redis)
    except Exception as e:
        logger.error(f"Traffic routing error: {e}")

    # Update click with campaign destination
    try:
        await db.clicks.update_one(
            {"_id": ObjectId(click_id)},
            {"$set": {"destination_url": destination}},
        )
    except Exception:
        pass

    # --- Queue background task for ML fraud check + CPC/earnings ---
    # Only queue for clean (non-flagged) clicks — flagged clicks are already processed
    if not is_flagged:
        try:
            from app.tasks.click_tasks import process_click
            click_data_for_task = {
                k: v.isoformat() if hasattr(v, "isoformat") else v
                for k, v in click_data.items()
            }
            process_click.delay(click_id, click_data_for_task)
        except Exception as e:
            logger.warning(f"Failed to queue click task: {e}")

    # --- Step 9: Final redirect ---
    return build_redirect(destination, referrer_suppression)


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
