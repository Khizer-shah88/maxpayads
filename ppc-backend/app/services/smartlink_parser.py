"""
Smartlink Parser Service
=========================
Parses incoming smartlink requests by trying all registered structures.
Handles backward compatibility with legacy hardcoded parameters.
"""

from typing import Optional, Tuple, Dict
from fastapi import Request
import logging

logger = logging.getLogger(__name__)


async def parse_smartlink_from_request(
    request: Request,
    db
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse a smartlink request and extract publisher_id, website_id (if any),
    and the structure name that matched.
    
    Args:
        request: FastAPI request object
        db: Database connection
    
    Returns:
        (publisher_param_value, website_param_value, structure_name)
        
    Logic:
    1. Get all active smartlink structures
    2. Try to match query parameters against each structure
    3. If no structure matches, fall back to legacy (pub, site)
    4. Return the extracted values
    """
    query_params = dict(request.query_params)
    
    # Fetch all active structures, sorted by default first
    structures = []
    try:
        cursor = db.smartlink_structures.find(
            {"status": "active"}
        ).sort([("is_default", -1), ("created_at", 1)])
        structures = await cursor.to_list(length=100)
    except Exception as e:
        logger.warning(f"Failed to load smartlink structures: {e}")
    
    # Try to match against registered structures
    for struct in structures:
        pub_param = struct.get("publisher_param", "pub")
        site_param = struct.get("website_param")
        include_site = struct.get("include_website", True)
        
        # Check if this structure matches the request
        if pub_param in query_params:
            pub_value = query_params[pub_param]
            site_value = None
            
            # Check for website parameter if structure includes it
            if include_site and site_param and site_param in query_params:
                site_value = query_params[site_param]
            
            logger.info(
                f"[Smartlink Parser] Matched structure '{struct.get('name', 'Unknown')}' "
                f"({pub_param}={pub_value}, {site_param}={site_value or 'N/A'})"
            )
            
            return pub_value, site_value, struct.get("name", "Unknown")
    
    # BACKWARD COMPATIBILITY: Fall back to legacy hardcoded parameters
    # This ensures old links with ?pub=X&site=Y still work even if no structures exist
    legacy_pub = query_params.get("pub")
    legacy_site = query_params.get("site")
    
    if legacy_pub:
        logger.info(
            f"[Smartlink Parser] Using legacy fallback (pub={legacy_pub}, site={legacy_site or 'N/A'})"
        )
        return legacy_pub, legacy_site, "Legacy (hardcoded)"
    
    # No match found
    logger.warning(f"[Smartlink Parser] No matching structure or legacy params in query: {list(query_params.keys())}")
    return None, None, None


async def get_default_structure(db) -> Optional[Dict]:
    """
    Get the default smartlink structure.
    
    Returns:
        The default structure document, or None if not found
    """
    try:
        # First try to find structure marked as default
        struct = await db.smartlink_structures.find_one(
            {"is_default": True, "status": "active"}
        )
        if struct:
            return struct
        
        # Fall back to any active structure
        struct = await db.smartlink_structures.find_one(
            {"status": "active"}
        )
        if struct:
            return struct
        
        # No structures exist - return a synthetic "Standard" structure for backward compatibility
        return {
            "name": "Standard (synthetic)",
            "publisher_param": "pub",
            "website_param": "site",
            "include_website": True,
            "extra_params": [],
            "is_default": True,
            "status": "active",
        }
    except Exception as e:
        logger.error(f"Failed to load default structure: {e}")
        return None


async def generate_smartlink_with_structure(
    db,
    publisher_id: str,
    website_id: Optional[str] = None,
    structure_id: Optional[str] = None,
    domain: Optional[str] = None,
    extra_params: Optional[Dict[str, str]] = None,
) -> str:
    """
    Generate a smartlink using a specific structure (or default).
    
    Args:
        db: Database connection
        publisher_id: Publisher identifier (public ID or ObjectId)
        website_id: Website identifier (optional)
        structure_id: Structure ID to use (optional, uses default if None)
        domain: Base domain URL (optional, uses default anchor if None)
        extra_params: Additional query parameters (optional)
    
    Returns:
        Complete smartlink URL
    """
    from urllib.parse import quote
    from bson import ObjectId
    
    # Get the structure
    structure = None
    if structure_id:
        try:
            structure = await db.smartlink_structures.find_one(
                {"_id": ObjectId(structure_id)}
            )
        except Exception:
            pass
    
    if not structure:
        structure = await get_default_structure(db)
    
    if not structure:
        raise ValueError("No smartlink structure available")
    
    # Resolve domain
    if not domain:
        from app.core.constants import DOMAIN_TYPE_ANCHOR
        from app.services.domain_service import resolve_domain_url
        domain = await resolve_domain_url(db, DOMAIN_TYPE_ANCHOR, None) or "https://clickspot.icu"
    
    domain = domain.rstrip("/")
    
    # Build query parameters
    pub_param = structure.get("publisher_param", "pub")
    site_param = structure.get("website_param", "site")
    include_site = structure.get("include_website", True)
    
    params = [f"{quote(pub_param)}={quote(publisher_id)}"]
    
    if include_site and website_id and site_param:
        params.append(f"{quote(site_param)}={quote(website_id)}")
    
    # Add structure's static extra params
    for extra in structure.get("extra_params", []):
        if isinstance(extra, dict) and extra.get("key"):
            params.append(f"{quote(str(extra['key']))}={quote(str(extra.get('value', '')))}")
    
    # Add dynamic extra params
    if extra_params:
        for key, value in extra_params.items():
            params.append(f"{quote(str(key))}={quote(str(value))}")
    
    smartlink = f"{domain}?{'&'.join(params)}"
    
    logger.info(
        f"[Smartlink Generator] Generated link using structure '{structure.get('name', 'Unknown')}': {smartlink}"
    )
    
    return smartlink
