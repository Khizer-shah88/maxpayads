"""
Migration 003: Add Stats Profile Indexes
=========================================

Creates indexes for the stats profile collections to ensure
fast queries and enforce uniqueness constraints.
"""

import logging

logger = logging.getLogger(__name__)


async def run(db):
    """Run migration to add stats profile indexes."""
    logger.info("Running migration 003: Add stats profile indexes")
    
    # stats_profiles collection
    await db.stats_profiles.create_index("slug", unique=True)
    await db.stats_profiles.create_index("publisher_id")
    await db.stats_profiles.create_index("status")
    await db.stats_profiles.create_index([("created_at", -1)])
    logger.info("  ✓ Created stats_profiles indexes")
    
    # stats_profile_impressions collection
    await db.stats_profile_impressions.create_index("profile_id")
    await db.stats_profile_impressions.create_index("profile_slug")
    await db.stats_profile_impressions.create_index([("created_at", -1)])
    await db.stats_profile_impressions.create_index([
        ("profile_id", 1),
        ("created_at", -1),
    ])
    logger.info("  ✓ Created stats_profile_impressions indexes")
    
    # stats_profile_clicks collection
    await db.stats_profile_clicks.create_index("profile_id")
    await db.stats_profile_clicks.create_index("profile_slug")
    await db.stats_profile_clicks.create_index("ip_address")
    await db.stats_profile_clicks.create_index("os")
    await db.stats_profile_clicks.create_index("is_valid")
    await db.stats_profile_clicks.create_index([("created_at", -1)])
    await db.stats_profile_clicks.create_index([
        ("profile_id", 1),
        ("created_at", -1),
    ])
    await db.stats_profile_clicks.create_index([
        ("profile_id", 1),
        ("os", 1),
    ])
    logger.info("  ✓ Created stats_profile_clicks indexes")
    
    # stats_profile_conversions collection
    await db.stats_profile_conversions.create_index("profile_id")
    await db.stats_profile_conversions.create_index("profile_slug")
    await db.stats_profile_conversions.create_index([("created_at", -1)])
    await db.stats_profile_conversions.create_index([
        ("profile_id", 1),
        ("created_at", -1),
    ])
    logger.info("  ✓ Created stats_profile_conversions indexes")
    
    # stats_profile_manual_conversions collection
    await db.stats_profile_manual_conversions.create_index("profile_slug")
    await db.stats_profile_manual_conversions.create_index("date")
    await db.stats_profile_manual_conversions.create_index([
        ("profile_slug", 1),
        ("date", 1),
    ], unique=True)  # One manual conversion per profile per date
    logger.info("  ✓ Created stats_profile_manual_conversions indexes")
    
    logger.info("Migration 003 completed successfully")
    return True


async def rollback(db):
    """Rollback migration 003."""
    logger.info("Rolling back migration 003")
    
    # Drop indexes (except _id which is automatic)
    try:
        await db.stats_profiles.drop_indexes()
        await db.stats_profile_impressions.drop_indexes()
        await db.stats_profile_clicks.drop_indexes()
        await db.stats_profile_conversions.drop_indexes()
        await db.stats_profile_manual_conversions.drop_indexes()
        logger.info("Migration 003 rollback completed")
    except Exception as e:
        logger.error(f"Migration 003 rollback error: {e}")
    
    return True
