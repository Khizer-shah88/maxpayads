"""
Smartlink Generator Service
============================
Generates configurable smartlinks with public publisher/website IDs.

Features:
- Supports both public IDs (PUB_XXX, SITE_XXX) and legacy ObjectIds
- Uses admin-defined smartlink structures for parameter names
- Configurable parameters (referrer, campaign, custom params)
- Multiple formats (standard, tag-based, custom structures)

The smartlink structure system allows admins to define the query parameter
names used in generated links, supporting various formats like:
- Standard: ?pub={PUB}&site={SITE}
- Tag + SID: ?tag={PUB}&sid={SITE}
- Tag Only: ?tag={PUB}
- Custom structures with extra static parameters
"""

from typing import Optional, Dict
from urllib.parse import urlencode
import logging

logger = logging.getLogger(__name__)


async def generate_smartlink(
    db,
    publisher_id: str,
    website_id: Optional[str] = None,
    base_url: Optional[str] = None,
    use_public_ids: bool = True,
    custom_params: Optional[Dict[str, str]] = None,
    referrer: Optional[str] = None,
    structure_id: Optional[str] = None,
) -> str:
    """
    Generate a smartlink URL for click tracking using registered structures.
    
    Args:
        db: Database connection
        publisher_id: Internal publisher _id
        website_id: Internal website _id (optional)
        base_url: Base URL for the link (e.g., "https://clickspot.icu")
        use_public_ids: If True, use public IDs instead of ObjectIds (default: True)
        custom_params: Additional query parameters (e.g., {"campaign": "summer2024"})
        referrer: Pre-set referrer value (optional)
        structure_id: Specific structure ID to use (optional, uses default if None)
    
    Returns:
        Complete smartlink URL
    """
    from app.services.smartlink_parser import generate_smartlink_with_structure
    from app.utils.public_id_utils import get_publisher_public_id, get_website_public_id
    
    # Get public IDs if requested
    if use_public_ids:
        pub_identifier = await get_publisher_public_id(db, publisher_id)
        if not pub_identifier:
            # Fallback to internal ID if no public_id exists (for legacy publishers)
            pub_identifier = publisher_id
            logger.warning(f"Publisher {publisher_id} has no public_id, using internal ID")
    else:
        pub_identifier = publisher_id
    
    site_identifier = None
    if website_id:
        if use_public_ids:
            site_identifier = await get_website_public_id(db, website_id)
            if not site_identifier:
                site_identifier = website_id
                logger.warning(f"Website {website_id} has no public_id, using internal ID")
        else:
            site_identifier = website_id
    
    # Build extra params
    extra_params = {}
    if referrer:
        extra_params["ref"] = referrer
    if custom_params:
        extra_params.update(custom_params)
    
    # Use structure-aware generator
    smartlink = await generate_smartlink_with_structure(
        db,
        publisher_id=pub_identifier,
        website_id=site_identifier,
        structure_id=structure_id,
        domain=base_url,
        extra_params=extra_params if extra_params else None,
    )
    
    return smartlink


async def generate_embed_code_with_smartlink(
    db,
    publisher_id: str,
    website_id: str,
    base_url: str,
    tracking_url: Optional[str] = None,
    use_public_ids: bool = True,
) -> Dict[str, str]:
    """
    Generate both embed code and smartlink for a website.
    
    Returns:
        {
            "embed_code": "<script>...</script>",
            "smart_link": "https://...",
            "pub_identifier": "PUB_XXX or ObjectId",
            "site_identifier": "SITE_XXX or ObjectId"
        }
    """
    from app.utils.public_id_utils import get_publisher_public_id, get_website_public_id
    
    # Get identifiers
    if use_public_ids:
        pub_id = await get_publisher_public_id(db, publisher_id) or publisher_id
        site_id = await get_website_public_id(db, website_id) or website_id
    else:
        pub_id = publisher_id
        site_id = website_id
    
    # Generate smartlink
    smart_link = await generate_smartlink(
        db, publisher_id, website_id, base_url, use_public_ids
    )
    
    # Generate embed code (script tag)
    script_base = tracking_url or base_url
    script_base = script_base.rstrip("/")
    embed_code = f'<script src="{script_base}/ad.js?pub={pub_id}&site={site_id}" async></script>'
    
    return {
        "embed_code": embed_code,
        "smart_link": smart_link,
        "pub_identifier": pub_id,
        "site_identifier": site_id,
    }


async def parse_smartlink_params(
    db,
    pub_param: str,
    site_param: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """
    Parse smartlink parameters and resolve to internal IDs.
    
    Args:
        pub_param: Publisher identifier (public ID or ObjectId)
        site_param: Website identifier (public ID or ObjectId)
    
    Returns:
        {
            "publisher_id": "internal_id",
            "website_id": "internal_id or None",
            "pub_type": "public_id or object_id",
            "site_type": "public_id or object_id or None"
        }
    """
    from app.utils.public_id_utils import resolve_publisher_id, resolve_website_id, is_public_id_format
    
    publisher_id = await resolve_publisher_id(db, pub_param)
    pub_type = "public_id" if is_public_id_format(pub_param, "publisher") else "object_id"
    
    website_id = None
    site_type = None
    if site_param:
        website_id = await resolve_website_id(db, site_param)
        site_type = "public_id" if is_public_id_format(site_param, "website") else "object_id"
    
    return {
        "publisher_id": publisher_id,
        "website_id": website_id,
        "pub_type": pub_type,
        "site_type": site_type,
    }
