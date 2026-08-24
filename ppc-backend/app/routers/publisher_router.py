from fastapi import APIRouter, Depends, Query, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timedelta
from bson import ObjectId
from app.schemas.publisher_schema import PublisherUpdate
from app.services.publisher_service import get_publisher_stats, update_publisher
from app.utils.date_utils import timestamp_range_query
from app.dependencies import get_db, get_redis_client, get_current_active_publisher
from app.core.exceptions import NotFoundError
from app.core.exceptions import ValidationError
import csv
import io
import os
import uuid
import aiofiles

VIDEO_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "videos")
os.makedirs(VIDEO_UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/publisher", tags=["Publisher"])


def _oid(id_str: str):
    try:
        return ObjectId(id_str)
    except Exception:
        return id_str


def _is_internal_url(url: str) -> bool:
    """Detect internal Docker/service URLs that should never appear in publisher embed codes."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or ""
    # Block common internal Docker service names and localhost-like hosts
    internal_patterns = ["fastapi", "backend", "api-service", "host.docker.internal"]
    if any(pat in host for pat in internal_patterns):
        return True
    return False


async def _get_base_url(db, request: Request, publisher_id: Optional[str] = None) -> str:
    """Get the link domain (anchor/redirect) for click URLs and smart links."""
    from app.services.domain_service import resolve_domain_url
    managed = await resolve_domain_url(db, "link", publisher_id)
    if managed:
        return managed.rstrip("/")
    doc = await db.system_settings.find_one({"key": "platform_domain"})
    if doc and doc.get("value"):
        return doc["value"].rstrip("/")
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        from urllib.parse import urlparse
        parsed = urlparse(origin)
        candidate = f"{parsed.scheme}://{parsed.netloc}"
        if not _is_internal_url(candidate):
            return candidate
    fallback = str(request.base_url).rstrip("/")
    if _is_internal_url(fallback):
        return "https://YOUR-DOMAIN.com"
    return fallback


async def _get_tracking_url(db, publisher_id: Optional[str] = None) -> str:
    """Get the click tracking domain for ad.js script serving."""
    from app.services.domain_service import resolve_domain_url
    managed = await resolve_domain_url(db, "link", publisher_id)
    if managed:
        return managed.rstrip("/")
    doc = await db.system_settings.find_one({"key": "click_tracking_domain"})
    if doc and doc.get("value"):
        return doc["value"].rstrip("/")
    return "https://clickspot.icu"


@router.get("/dashboard")
async def publisher_dashboard(
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    stats = await get_publisher_stats(current_user["id"], db)
    return {"success": True, "stats": stats, "publisher": {
        "name": current_user["name"],
        "email": current_user["email"],
        "status": current_user["status"],
        "balance": current_user.get("balance", 0),
        "payment_method": current_user.get("payment_method"),
        "payment_details": current_user.get("payment_details"),
    }}


@router.get("/reports")
async def publisher_reports(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    website_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    os: Optional[str] = Query(None),
    browser: Optional[str] = Query(None),
    country_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    query = {"publisher_id": current_user["id"]}
    if website_id:
        query["website_id"] = website_id
    if status:
        query["status"] = status
    if device_type:
        query["device_type"] = device_type
    if os:
        query["os"] = {"$regex": os, "$options": "i"}
    if browser:
        query["browser"] = {"$regex": browser, "$options": "i"}
    if country_code:
        query["country_code"] = country_code.upper()
    tr = timestamp_range_query(date_from, date_to)
    if tr:
        query["timestamp"] = tr
    skip = (page - 1) * limit
    total = await db.clicks.count_documents(query)
    cursor = db.clicks.find(query).skip(skip).limit(limit).sort("timestamp", -1)
    clicks = await cursor.to_list(length=None)

    # Resolve website_id -> domain
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

    for c in clicks:
        c["id"] = str(c.pop("_id"))
        if c.get("website_id") and c["website_id"] in website_domains:
            c["website_domain"] = website_domains[c["website_id"]]
        if "timestamp" in c:
            c["timestamp"] = c["timestamp"].isoformat()
        if c.get("processed_at"):
            c["processed_at"] = c["processed_at"].isoformat()

    # Full-window summary (independent of pagination) so the stat cards reflect
    # the whole filtered range, not just the current page of rows.
    valid_count = await db.clicks.count_documents({**query, "status": "valid"}) if not status else (total if status == "valid" else 0)
    invalid_count = await db.clicks.count_documents({**query, "status": "invalid"}) if not status else (total if status == "invalid" else 0)
    earn_pipe = [{"$match": query}, {"$group": {"_id": None, "total": {"$sum": "$earnings"}}}]
    earn_res = await db.clicks.aggregate(earn_pipe).to_list(length=1)
    earnings_total = earn_res[0]["total"] if earn_res else 0.0
    summary = {
        "total": total,
        "valid": valid_count,
        "invalid": invalid_count,
        "earnings": round(earnings_total, 4),
    }

    return {"success": True, "total": total, "page": page, "limit": limit,
            "pages": (total + limit - 1) // limit, "clicks": clicks, "summary": summary}


@router.get("/reports/export-csv")
async def publisher_reports_csv(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    website_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    os: Optional[str] = Query(None),
    browser: Optional[str] = Query(None),
    country_code: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    """Export publisher's own click data as CSV with same filters as stats page."""
    query = {"publisher_id": current_user["id"]}
    if website_id:
        query["website_id"] = website_id
    if status:
        query["status"] = status
    if device_type:
        query["device_type"] = device_type
    if os:
        query["os"] = {"$regex": os, "$options": "i"}
    if browser:
        query["browser"] = {"$regex": browser, "$options": "i"}
    if country_code:
        query["country_code"] = country_code.upper()
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
    writer = csv.writer(output)
    writer.writerow(["Time", "Website", "Country", "Device", "OS", "Browser", "Status", "CPC", "Earnings", "Fraud Reason"])
    for c in clicks:
        wid = c.get("website_id", "")
        domain = website_domains.get(wid, wid) if wid else ""
        writer.writerow([
            str(c.get("timestamp", "")), domain,
            c.get("country_code", ""), c.get("device_type", ""),
            c.get("os", ""), c.get("browser", ""), c.get("status", ""),
            c.get("cpc", 0), c.get("earnings", 0), c.get("fraud_reason", ""),
        ])
    output.seek(0)
    filename = f"my_reports_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/clicks-trend")
async def publisher_clicks_trend(
    period: str = Query("7d"),
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    """Publisher's own daily click trend (no admin required)."""
    days_map = {"7d": 7, "30d": 30, "90d": 90}
    days = days_map.get(period, 7)
    since = datetime.utcnow() - timedelta(days=days)
    pipeline = [
        {"$match": {"publisher_id": current_user["id"], "timestamp": {"$gte": since}}},
        {"$group": {
            "_id": {
                "year": {"$year": "$timestamp"},
                "month": {"$month": "$timestamp"},
                "day": {"$dayOfMonth": "$timestamp"},
            },
            "clicks": {"$sum": 1},
            "valid_clicks": {"$sum": {"$cond": ["$is_valid", 1, 0]}},
            "invalid_clicks": {"$sum": {"$cond": [{"$not": "$is_valid"}, 1, 0]}},
            "earnings": {"$sum": "$earnings"},
        }},
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


@router.get("/websites")
async def get_websites(
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
    request: Request = None,
):
    cursor = db.websites.find({"publisher_id": current_user["id"]})
    websites = await cursor.to_list(length=None)
    base_domain = await _get_base_url(db, request, current_user["id"])
    if base_domain == "https://YOUR-DOMAIN.com":
        doc = await db.system_settings.find_one({"key": "platform_domain"})
        if doc and doc.get("value"):
            base_domain = doc["value"].rstrip("/")
    for w in websites:
        w["id"] = str(w.pop("_id"))
        if w.get("updated_at"):
            w["updated_at"] = w["updated_at"].isoformat()
        if w.get("created_at"):
            w["created_at"] = w["created_at"].isoformat()
        w["embed_code"] = (
            f'<script src="{base_domain}/ad.js?pub={current_user["id"]}&site={w["id"]}" async></script>'
        )
    return {"success": True, "websites": websites}


@router.post("/websites", status_code=201)
async def add_website(
    data: dict,
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    domain = data.get("domain", "").strip().lower().replace("https://", "").replace("http://", "")
    name = data.get("name", domain)
    website = {
        "publisher_id": current_user["id"],
        "domain": domain,
        "name": name,
        "status": "active",
        "assigned_campaign_id": None,
        "total_clicks": 0,
        "valid_clicks": 0,
        "invalid_clicks": 0,
        "total_earnings": 0.0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    result = await db.websites.insert_one(website)
    return {"success": True, "website_id": str(result.inserted_id), "message": "Website added"}


@router.delete("/websites/{website_id}")
async def remove_website(
    website_id: str,
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    result = await db.websites.delete_one(
        {"_id": _oid(website_id), "publisher_id": current_user["id"]}
    )
    if result.deleted_count == 0:
        result = await db.websites.delete_one(
            {"_id": website_id, "publisher_id": current_user["id"]}
        )
    if result.deleted_count == 0:
        raise NotFoundError("Website")
    return {"success": True, "message": "Website removed"}


@router.get("/ad-unit/{website_id}")
async def get_ad_unit(
    website_id: str,
    request: Request,
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    website = await db.websites.find_one(
        {"_id": _oid(website_id), "publisher_id": current_user["id"]}
    )
    if not website:
        website = await db.websites.find_one(
            {"_id": website_id, "publisher_id": current_user["id"]}
        )
    if not website:
        raise NotFoundError("Website")
    base_url = await _get_base_url(db, request, current_user["id"])
    tracking_url = await _get_tracking_url(db, current_user["id"])

    # Get saved ad settings for this website
    ad_settings = await db.ad_settings.find_one({
        "website_id": website_id,
        "publisher_id": current_user["id"],
    })
    if not ad_settings:
        ad_settings = {}
    else:
        ad_settings["id"] = str(ad_settings.pop("_id", ""))

    ad_type = ad_settings.get("ad_type", "banner")
    embed_code = _generate_embed_code(
        ad_type, ad_settings, base_url, current_user["id"], website_id,
        tracking_url=tracking_url,
    )
    smart_link = f"{base_url}?pub={current_user['id']}&site={website_id}"

    return {
        "success": True,
        "website_id": website_id,
        "domain": website.get("domain"),
        "embed_code": embed_code,
        "smart_link": smart_link,
        "ad_settings": ad_settings,
    }


@router.post("/ad-unit/{website_id}/settings")
async def save_ad_settings(
    website_id: str,
    data: dict,
    request: Request,
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    """Save ad customization settings for a website."""
    website = await db.websites.find_one(
        {"_id": _oid(website_id), "publisher_id": current_user["id"]}
    )
    if not website:
        website = await db.websites.find_one(
            {"_id": website_id, "publisher_id": current_user["id"]}
        )
    if not website:
        raise NotFoundError("Website")

    ad_type = data.get("ad_type", "banner")
    settings = {
        "website_id": website_id,
        "publisher_id": current_user["id"],
        "ad_type": ad_type,
        "button_text": data.get("button_text", "Download Now"),
        "text_color": data.get("text_color", "#FFFFFF"),
        "bg_color": data.get("bg_color", "#000000"),
        "button_color": data.get("button_color", "#5465FF"),
        "button_text_color": data.get("button_text_color", "#FFFFFF"),
        "banner_text": data.get("banner_text", "Advertisement"),
        "banner_width": data.get("banner_width", "728"),
        "banner_height": data.get("banner_height", "90"),
        "popup_title": data.get("popup_title", "Special Offer!"),
        "popup_message": data.get("popup_message", "Click here for an exclusive deal"),
        "popup_delay": data.get("popup_delay", 3),
        "video_placeholder_text": data.get("video_placeholder_text", "Watch Now"),
        "font_size": data.get("font_size", "16"),
        "border_radius": data.get("border_radius", "8"),
        "updated_at": datetime.utcnow(),
    }

    await db.ad_settings.update_one(
        {"website_id": website_id, "publisher_id": current_user["id"]},
        {"$set": settings, "$setOnInsert": {"created_at": datetime.utcnow()}},
        upsert=True,
    )

    base_url = await _get_base_url(db, request, current_user["id"])
    tracking_url = await _get_tracking_url(db, current_user["id"])
    embed_code = _generate_embed_code(
        ad_type, settings, base_url, current_user["id"], website_id,
        tracking_url=tracking_url,
    )
    smart_link = f"{base_url}?pub={current_user['id']}&site={website_id}"

    return {
        "success": True,
        "message": "Ad settings saved",
        "embed_code": embed_code,
        "smart_link": smart_link,
    }


def _generate_embed_code(
    ad_type: str, settings: dict, base_url: str, pub_id: str, site_id: str,
    tracking_url: str = None,
) -> str:
    """Generate HTML embed code based on ad type and settings."""
    click_url = f"{base_url}?pub={pub_id}&site={site_id}"
    # Use base_url (platform domain) for script URL to avoid exposing tracking domains
    script_url = f"{base_url}/ad.js?pub={pub_id}&site={site_id}&type={ad_type}"

    text_color = settings.get("text_color", "#FFFFFF")
    bg_color = settings.get("bg_color", "#000000")
    button_color = settings.get("button_color", "#5465FF")
    button_text_color = settings.get("button_text_color", "#FFFFFF")
    font_size = settings.get("font_size", "16")
    border_radius = settings.get("border_radius", "8")

    if ad_type == "button":
        btn_text = settings.get("button_text", "Download Now")
        return (
            f'<center><style>.ppc-btn{{background-color:{button_color};border:none;color:{button_text_color};'
            f'padding:15px 32px;text-align:center;text-decoration:none;display:inline-block;'
            f'font-size:{font_size}px;font-weight:bold;margin:4px 2px;cursor:pointer;'
            f'border-radius:{border_radius}px;transition:0.3s;}}'
            f'.ppc-btn:hover{{opacity:0.85;box-shadow:0 12px 16px 0 rgba(0,0,0,0.24),0 17px 50px 0 rgba(0,0,0,0.19);}}'
            f'</style><a href="{click_url}" target="_blank" rel="noopener" class="ppc-btn">'
            f'{btn_text}</a></center>\n'
            f'<script data-cfasync="false" async type="text/javascript" src="{script_url}"></script>'
        )

    elif ad_type == "popup":
        popup_title = settings.get("popup_title", "Special Offer!")
        popup_msg = settings.get("popup_message", "Click here for an exclusive deal")
        popup_delay = settings.get("popup_delay", 3)
        return (
            f'<script data-cfasync="false" type="text/javascript">\n'
            f'(function(){{\n'
            f'  setTimeout(function(){{\n'
            f'    var ov=document.createElement("div");\n'
            f'    ov.style.cssText="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:99999;display:flex;align-items:center;justify-content:center;";\n'
            f'    var bx=document.createElement("div");\n'
            f'    bx.style.cssText="background:{bg_color};border-radius:{border_radius}px;padding:30px 40px;max-width:420px;width:90%;text-align:center;position:relative;box-shadow:0 20px 60px rgba(0,0,0,0.3);";\n'
            f'    var cl=document.createElement("span");\n'
            f'    cl.textContent="\\u00D7";cl.style.cssText="position:absolute;top:10px;right:15px;font-size:24px;cursor:pointer;color:{text_color};opacity:0.7;";\n'
            f'    cl.onclick=function(){{ov.remove();}};\n'
            f'    var t=document.createElement("h3");\n'
            f'    t.textContent="{popup_title}";t.style.cssText="color:{text_color};margin:0 0 10px;font-size:22px;font-family:sans-serif;";\n'
            f'    var m=document.createElement("p");\n'
            f'    m.textContent="{popup_msg}";m.style.cssText="color:{text_color};opacity:0.8;margin:0 0 20px;font-size:14px;font-family:sans-serif;";\n'
            f'    var b=document.createElement("a");\n'
            f'    b.href="{click_url}";b.target="_blank";b.rel="noopener";\n'
            f'    b.textContent="{settings.get("button_text", "Claim Now")}";'
            f'b.style.cssText="display:inline-block;background:{button_color};color:{button_text_color};padding:12px 30px;border-radius:{border_radius}px;text-decoration:none;font-weight:bold;font-size:{font_size}px;font-family:sans-serif;";\n'
            f'    bx.appendChild(cl);bx.appendChild(t);bx.appendChild(m);bx.appendChild(b);\n'
            f'    ov.appendChild(bx);document.body.appendChild(ov);\n'
            f'    ov.addEventListener("click",function(e){{if(e.target===ov)ov.remove();}});\n'
            f'  }},{popup_delay * 1000});\n'
            f'}})();\n'
            f'</script>'
        )

    elif ad_type == "video":
        vid_text = settings.get("video_placeholder_text", "Watch Now")
        return (
            f'<div style="max-width:480px;margin:10px auto;background:{bg_color};border-radius:{border_radius}px;overflow:hidden;font-family:sans-serif;">\n'
            f'  <a href="{click_url}" target="_blank" rel="noopener" style="display:block;position:relative;text-decoration:none;">\n'
            f'    <div style="aspect-ratio:16/9;background:linear-gradient(135deg,{bg_color},{button_color});display:flex;align-items:center;justify-content:center;">\n'
            f'      <div style="width:64px;height:64px;background:rgba(255,255,255,0.9);border-radius:50%;display:flex;align-items:center;justify-content:center;">\n'
            f'        <div style="width:0;height:0;border-top:14px solid transparent;border-bottom:14px solid transparent;border-left:22px solid {button_color};margin-left:4px;"></div>\n'
            f'      </div>\n'
            f'    </div>\n'
            f'    <div style="padding:12px 16px;display:flex;align-items:center;justify-content:space-between;">\n'
            f'      <span style="color:{text_color};font-weight:bold;font-size:{font_size}px;">{vid_text}</span>\n'
            f'      <span style="background:{button_color};color:{button_text_color};padding:6px 16px;border-radius:{border_radius}px;font-size:13px;font-weight:bold;">Play</span>\n'
            f'    </div>\n'
            f'  </a>\n'
            f'</div>\n'
            f'<script data-cfasync="false" async type="text/javascript" src="{script_url}"></script>'
        )

    else:  # banner (default)
        banner_text = settings.get("banner_text", "Advertisement")
        banner_w = settings.get("banner_width", "728")
        banner_h = settings.get("banner_height", "90")
        return (
            f'<div style="max-width:{banner_w}px;height:{banner_h}px;margin:10px auto;overflow:hidden;">\n'
            f'  <a href="{click_url}" target="_blank" rel="noopener" style="display:flex;align-items:center;justify-content:center;width:100%;height:100%;'
            f'background:linear-gradient(135deg,{bg_color},{button_color});border-radius:{border_radius}px;text-decoration:none;font-family:sans-serif;">\n'
            f'    <span style="color:{text_color};font-weight:bold;font-size:{font_size}px;">{banner_text}</span>\n'
            f'  </a>\n'
            f'</div>\n'
            f'<script data-cfasync="false" async type="text/javascript" src="{script_url}"></script>'
        )


@router.get("/videos")
async def get_videos(
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    cursor = db.publisher_videos.find({"publisher_id": current_user["id"]}).sort("created_at", -1)
    videos = await cursor.to_list(length=None)
    for v in videos:
        v["id"] = str(v.pop("_id"))
        if v.get("created_at"):
            v["created_at"] = v["created_at"].isoformat() if hasattr(v["created_at"], "isoformat") else str(v["created_at"])
    return {"success": True, "videos": videos}


@router.post("/videos", status_code=201)
async def add_video(
    data: dict,
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    title = data.get("title", "").strip()
    video_url = data.get("video_url", "").strip()
    description = data.get("description", "").strip()
    if not title or not video_url:
        raise ValidationError("Title and video URL are required")
    website_id = data.get("website_id", "").strip()
    doc = {
        "publisher_id": current_user["id"],
        "title": title,
        "video_url": video_url,
        "description": description,
        "website_id": website_id if website_id else None,
        "type": "link",
        "status": "pending",
        "created_at": datetime.utcnow(),
    }
    result = await db.publisher_videos.insert_one(doc)
    return {"success": True, "video_id": str(result.inserted_id), "message": "Video added"}


@router.post("/videos/upload", status_code=201)
async def upload_video(
    title: str = Form(...),
    description: str = Form(""),
    website_id: str = Form(""),
    video_file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    if not title.strip():
        raise ValidationError("Title is required")
    ext = os.path.splitext(video_file.filename or "")[1].lower()
    # 200MB max
    contents = await video_file.read()
    if len(contents) > 200 * 1024 * 1024:
        raise ValidationError("File must be under 200MB")
    filename = f"{current_user['id']}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(VIDEO_UPLOAD_DIR, filename)
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(contents)
    file_url = f"/uploads/videos/{filename}"
    doc = {
        "publisher_id": current_user["id"],
        "title": title.strip(),
        "video_url": file_url,
        "description": description.strip(),
        "website_id": website_id.strip() if website_id.strip() else None,
        "type": "upload",
        "file_size": len(contents),
        "status": "pending",
        "created_at": datetime.utcnow(),
    }
    result = await db.publisher_videos.insert_one(doc)
    return {"success": True, "video_id": str(result.inserted_id), "message": "Video uploaded", "video_url": file_url}


@router.delete("/videos/{video_id}")
async def delete_video(
    video_id: str,
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    result = await db.publisher_videos.delete_one(
        {"_id": _oid(video_id), "publisher_id": current_user["id"]}
    )
    if result.deleted_count == 0:
        raise NotFoundError("Video")
    return {"success": True, "message": "Video deleted"}


@router.patch("/profile")
async def update_profile(
    data: PublisherUpdate,
    current_user: dict = Depends(get_current_active_publisher),
    db=Depends(get_db),
):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    await update_publisher(current_user["id"], update_data, db)
    return {"success": True, "message": "Profile updated"}
