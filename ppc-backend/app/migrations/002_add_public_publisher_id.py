"""
Migration 002: Add Public Publisher ID System
============================================== 
Date: 2026-09-02
Description: Implements Phase 2 - unique public publisher IDs for smartlinks

Changes:
- Add public_id field to publishers collection (unique, human-readable)
- Add public_id field to websites collection (unique, human-readable)
- Create indexes for fast public_id lookups
- Generate public_ids for existing records (backward compatible)
- Add creator tracking (is_admin_created, created_by fields)

Rollback: Safe - new fields are optional, existing pub/site params still work
"""

import logging
from datetime import datetime
from bson import ObjectId
import secrets
import string

logger = logging.getLogger(__name__)

# Migration version tracking
MIGRATION_VERSION = 2
MIGRATION_NAME = "add_public_publisher_id"


async def generate_public_id(prefix: str, length: int = 8) -> str:
    """Generate a unique public ID with prefix (e.g., PUB_ABC12XYZ, SITE_XYZ789AB)."""
    chars = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(length))
    return f"{prefix}_{random_part}"


async def is_public_id_unique(db, collection_name: str, public_id: str) -> bool:
    """Check if public_id is unique in the specified collection."""
    count = await db[collection_name].count_documents({"public_id": public_id})
    return count == 0


async def generate_unique_public_id(db, collection_name: str, prefix: str, max_attempts: int = 10) -> str:
    """Generate a unique public ID with retry logic."""
    for attempt in range(max_attempts):
        public_id = await generate_public_id(prefix)
        if await is_public_id_unique(db, collection_name, public_id):
            return public_id
    raise Exception(f"Failed to generate unique public_id after {max_attempts} attempts")


async def up(db):
    """Apply migration: Add public_id system to publishers and websites."""
    logger.info(f"Running migration {MIGRATION_VERSION}: {MIGRATION_NAME}")
    
    # =====================
    # STEP 1: Publishers
    # =====================
    logger.info("Step 1: Adding public_id to publishers...")
    
    # Create index for public_id (unique, sparse for backward compatibility)
    await db.publishers.create_index("public_id", unique=True, sparse=True)
    logger.info("  ✓ Created unique index on publishers.public_id")
    
    # Count publishers without public_id
    publishers_to_migrate = await db.publishers.count_documents({"public_id": {"$exists": False}})
    logger.info(f"  Found {publishers_to_migrate} publishers without public_id")
    
    # Generate public_ids for existing publishers
    if publishers_to_migrate > 0:
        cursor = db.publishers.find({"public_id": {"$exists": False}})
        migrated_count = 0
        async for publisher in cursor:
            pub_id = str(publisher["_id"])
            public_id = await generate_unique_public_id(db, "publishers", "PUB")
            
            # Default: self-registered (created via /auth/register)
            # Only admin-created publishers will have is_admin_created=True
            is_admin_created = False
            created_by = None
            
            await db.publishers.update_one(
                {"_id": publisher["_id"]},
                {
                    "$set": {
                        "public_id": public_id,
                        "is_admin_created": is_admin_created,
                        "created_by": created_by,
                        "updated_at": datetime.utcnow(),
                    }
                }
            )
            migrated_count += 1
            if migrated_count % 10 == 0:
                logger.info(f"  Migrated {migrated_count}/{publishers_to_migrate} publishers...")
        
        logger.info(f"  ✓ Generated public_ids for {migrated_count} publishers")
    
    # =====================
    # STEP 2: Websites
    # =====================
    logger.info("Step 2: Adding public_id to websites...")
    
    # Create index for public_id (unique, sparse)
    await db.websites.create_index("public_id", unique=True, sparse=True)
    logger.info("  ✓ Created unique index on websites.public_id")
    
    # Count websites without public_id
    websites_to_migrate = await db.websites.count_documents({"public_id": {"$exists": False}})
    logger.info(f"  Found {websites_to_migrate} websites without public_id")
    
    # Generate public_ids for existing websites
    if websites_to_migrate > 0:
        cursor = db.websites.find({"public_id": {"$exists": False}})
        migrated_count = 0
        async for website in cursor:
            public_id = await generate_unique_public_id(db, "websites", "SITE")
            
            await db.websites.update_one(
                {"_id": website["_id"]},
                {
                    "$set": {
                        "public_id": public_id,
                        "updated_at": datetime.utcnow(),
                    }
                }
            )
            migrated_count += 1
            if migrated_count % 10 == 0:
                logger.info(f"  Migrated {migrated_count}/{websites_to_migrate} websites...")
        
        logger.info(f"  ✓ Generated public_ids for {migrated_count} websites")
    
    # =====================
    # STEP 3: Migration Log
    # =====================
    logger.info("Step 3: Recording migration...")
    
    await db.migrations.insert_one({
        "version": MIGRATION_VERSION,
        "name": MIGRATION_NAME,
        "applied_at": datetime.utcnow(),
        "description": "Add public_id system for publishers and websites",
        "changes": [
            "Added public_id field to publishers (unique, indexed)",
            "Added public_id field to websites (unique, indexed)",
            "Added is_admin_created, created_by fields to publishers",
            "Generated public_ids for existing records",
        ]
    })
    
    logger.info(f"✓ Migration {MIGRATION_VERSION} completed successfully")


async def down(db):
    """Rollback migration: Remove public_id fields (optional, for development)."""
    logger.info(f"Rolling back migration {MIGRATION_VERSION}: {MIGRATION_NAME}")
    
    # Drop indexes
    try:
        await db.publishers.drop_index("public_id_1")
        logger.info("  ✓ Dropped publishers.public_id index")
    except Exception as e:
        logger.warning(f"  Could not drop publishers.public_id index: {e}")
    
    try:
        await db.websites.drop_index("public_id_1")
        logger.info("  ✓ Dropped websites.public_id index")
    except Exception as e:
        logger.warning(f"  Could not drop websites.public_id index: {e}")
    
    # Remove fields (optional - commented out for safety)
    # await db.publishers.update_many({}, {"$unset": {"public_id": "", "is_admin_created": "", "created_by": ""}})
    # await db.websites.update_many({}, {"$unset": {"public_id": ""}})
    
    # Remove migration log
    await db.migrations.delete_one({"version": MIGRATION_VERSION, "name": MIGRATION_NAME})
    
    logger.info(f"✓ Migration {MIGRATION_VERSION} rolled back")


async def run(db, direction: str = "up"):
    """Run migration in specified direction (up/down)."""
    if direction == "up":
        await up(db)
    elif direction == "down":
        await down(db)
    else:
        raise ValueError(f"Invalid migration direction: {direction}")
