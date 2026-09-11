from typing import Optional
from bson import ObjectId
from app.core.constants import COUNTRY_CPC_RATES, DEFAULT_REVENUE_SHARE
from app.config import settings
import logging

logger = logging.getLogger(__name__)


def _oid(id_str: str):
    try:
        return ObjectId(id_str)
    except Exception:
        return id_str


async def calculate_cpc(
    publisher_id: str,
    country_code: Optional[str],
    device_type: Optional[str],
    db,
) -> float:
    """
    Calculate CPC based on priority:
    1. Publisher custom CPC (highest priority)
    2. Country-specific CPC from system settings
    3. Global country rate from constants
    4. Global default CPC
    """
    # Resolve the base CPC by priority, THEN apply the device modifier once so
    # mobile/tablet pricing is consistent no matter which source set the rate.
    # (Previously the modifier only ran on the constants fallback, so any admin
    #  country override or publisher custom CPC silently dropped device pricing.)
    cpc: Optional[float] = None

    # Country CPC settings and rate tables store uppercase ISO codes
    # (admin writes them via set_country_cpc(code.upper(), ...)); normalize the
    # visitor's code the same way so a lower/mixed-case input still resolves.
    country_key = (country_code or "").strip().upper() or None

    # 1. Publisher custom CPC (highest priority)
    publisher = await db.publishers.find_one({"_id": _oid(publisher_id)})
    if not publisher:
        publisher = await db.publishers.find_one({"_id": publisher_id})
    if publisher and publisher.get("custom_cpc") is not None:
        cpc = float(publisher["custom_cpc"])
        logger.debug(f"Using custom CPC {cpc} for publisher {publisher_id}")

    # 2. Country-specific CPC from system settings
    if cpc is None and country_key:
        setting = await db.system_settings.find_one({"key": f"cpc_country_{country_key}"})
        if setting:
            cpc = float(setting["value"])
            logger.debug(f"Using country setting CPC {cpc} for {country_key}")

    # 3. Global country rate from constants
    if cpc is None and country_key and country_key in COUNTRY_CPC_RATES:
        cpc = COUNTRY_CPC_RATES[country_key]

    # 4. Global default CPC
    if cpc is None:
        cpc = COUNTRY_CPC_RATES.get("DEFAULT", settings.DEFAULT_CPC)

    # Apply device type modifier uniformly to the resolved base rate.
    if device_type == "mobile":
        cpc *= 0.85
    elif device_type == "tablet":
        cpc *= 0.90

    return round(cpc, 6)


async def get_global_cpc_settings(db) -> dict:
    """Get country CPC overrides for the admin panel.

    Scoped to ``cpc_country_*`` keys only — the admin CPC page strips that exact
    prefix, so any other ``cpc_*`` setting would otherwise render as a bogus
    country row with a raw key as its code.
    """
    cursor = db.system_settings.find({"key": {"$regex": "^cpc_country_"}})
    settings_list = await cursor.to_list(length=None)
    return {s["key"]: s["value"] for s in settings_list}


async def set_country_cpc(country_code: str, cpc: float, db):
    """Set country-specific CPC in system settings."""
    await db.system_settings.update_one(
        {"key": f"cpc_country_{country_code}"},
        {
            "$set": {
                "key": f"cpc_country_{country_code}",
                "value": cpc,
                "description": f"CPC rate for {country_code}",
            }
        },
        upsert=True,
    )


async def delete_country_cpc(country_code: str, db):
    """Remove country-specific CPC override."""
    await db.system_settings.delete_one({"key": f"cpc_country_{country_code}"})
