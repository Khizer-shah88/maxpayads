"""
Public ID Utilities
===================
Generate and resolve unique human-readable public IDs for publishers and websites.

Format:
- Publishers: PUB_XXXXXXXX (e.g., PUB_A1B2C3D4)
- Websites: SITE_XXXXXXXX (e.g., SITE_X7Y8Z9W0)

Public IDs are:
- Unique across their collection
- URL-safe (uppercase letters + digits)
- Human-readable
- 8 characters random part
"""

import secrets
import string
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Constants
PUB_PREFIX = "PUB"
SITE_PREFIX = "SITE"
ID_LENGTH = 8
CHARS = string.ascii_uppercase + string.digits


def generate_public_id(prefix: str, length: int = ID_LENGTH) -> str:
    """Generate a public ID with the given prefix."""
    random_part = ''.join(secrets.choice(CHARS) for _ in range(length))
    return f"{prefix}_{random_part}"


async def is_public_id_unique(db, collection_name: str, public_id: str) -> bool:
    """Check if a public ID is unique in the specified collection."""
    count = await db[collection_name].count_documents({"public_id": public_id})
    return count == 0


async def generate_unique_publisher_id(db, max_attempts: int = 10) -> str:
    """Generate a unique publisher public ID."""
    for _ in range(max_attempts):
        public_id = generate_public_id(PUB_PREFIX)
        if await is_public_id_unique(db, "publishers", public_id):
            return public_id
    raise Exception("Failed to generate unique publisher public_id after max attempts")


async def generate_unique_website_id(db, max_attempts: int = 10) -> str:
    """Generate a unique website public ID."""
    for _ in range(max_attempts):
        public_id = generate_public_id(SITE_PREFIX)
        if await is_public_id_unique(db, "websites", public_id):
            return public_id
    raise Exception("Failed to generate unique website public_id after max attempts")


async def resolve_publisher_id(db, identifier: str) -> Optional[str]:
    """
    Resolve a publisher identifier to internal MongoDB _id.
    Accepts:
    - MongoDB ObjectId string
    - Public ID (PUB_XXXXXXXX)
    
    Returns internal _id string or None if not found.
    """
    from bson import ObjectId
    
    # Try public_id lookup first (most common case for new links)
    if identifier.startswith(PUB_PREFIX):
        publisher = await db.publishers.find_one({"public_id": identifier})
        if publisher:
            return str(publisher["_id"])
    
    # Fallback: Try as MongoDB ObjectId (backward compatibility)
    try:
        publisher = await db.publishers.find_one({"_id": ObjectId(identifier)})
        if publisher:
            return str(publisher["_id"])
    except Exception:
        pass
    
    # Last resort: Try as string _id (some legacy records may use string IDs)
    publisher = await db.publishers.find_one({"_id": identifier})
    if publisher:
        return str(publisher["_id"])
    
    return None


async def resolve_website_id(db, identifier: str) -> Optional[str]:
    """
    Resolve a website identifier to internal MongoDB _id.
    Accepts:
    - MongoDB ObjectId string
    - Public ID (SITE_XXXXXXXX)
    
    Returns internal _id string or None if not found.
    """
    from bson import ObjectId
    
    # Try public_id lookup first
    if identifier.startswith(SITE_PREFIX):
        website = await db.websites.find_one({"public_id": identifier})
        if website:
            return str(website["_id"])
    
    # Fallback: Try as MongoDB ObjectId
    try:
        website = await db.websites.find_one({"_id": ObjectId(identifier)})
        if website:
            return str(website["_id"])
    except Exception:
        pass
    
    # Last resort: Try as string _id
    website = await db.websites.find_one({"_id": identifier})
    if website:
        return str(website["_id"])
    
    return None


async def get_publisher_public_id(db, internal_id: str) -> Optional[str]:
    """Get public_id for a publisher given their internal _id."""
    from bson import ObjectId
    
    try:
        oid = ObjectId(internal_id)
    except Exception:
        oid = internal_id
    
    publisher = await db.publishers.find_one({"_id": oid}, {"public_id": 1})
    return publisher.get("public_id") if publisher else None


async def get_website_public_id(db, internal_id: str) -> Optional[str]:
    """Get public_id for a website given their internal _id."""
    from bson import ObjectId
    
    try:
        oid = ObjectId(internal_id)
    except Exception:
        oid = internal_id
    
    website = await db.websites.find_one({"_id": oid}, {"public_id": 1})
    return website.get("public_id") if website else None


def is_public_id_format(identifier: str, id_type: str = "any") -> bool:
    """
    Check if a string matches public ID format.
    
    Args:
        identifier: The ID to check
        id_type: "publisher", "website", or "any"
    
    Returns:
        True if the identifier matches the expected public ID format
    """
    if not identifier or not isinstance(identifier, str):
        return False
    
    if id_type == "publisher":
        # Check prefix and minimum reasonable length (at least 7 chars after prefix)
        return identifier.startswith(f"{PUB_PREFIX}_") and len(identifier) >= len(PUB_PREFIX) + 1 + 7
    elif id_type == "website":
        # Check prefix and minimum reasonable length (at least 7 chars after prefix)
        return identifier.startswith(f"{SITE_PREFIX}_") and len(identifier) >= len(SITE_PREFIX) + 1 + 7
    else:  # any
        return (identifier.startswith(f"{PUB_PREFIX}_") or identifier.startswith(f"{SITE_PREFIX}_"))
