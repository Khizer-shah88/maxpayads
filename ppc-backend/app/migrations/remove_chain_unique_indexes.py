"""
Migration: Remove unique indexes from redirect_chains collection

This migration removes any unique indexes on the redirect_chains collection
that were preventing multiple chains from using the same anchor domain or name.

Run automatically on server startup.
"""

import logging

logger = logging.getLogger(__name__)

async def migrate(db):
    """Remove problematic unique indexes from redirect_chains"""
    try:
        # Get all indexes on redirect_chains
        indexes = await db.redirect_chains.list_indexes().to_list(length=None)
        
        logger.info(f"Found {len(indexes)} indexes on redirect_chains collection")
        
        # Find and drop any unique indexes (except _id_)
        dropped = []
        for index in indexes:
            index_name = index.get('name', '')
            is_unique = index.get('unique', False)
            
            # Never drop the _id index
            if index_name == '_id_':
                continue
            
            # Drop any unique index
            if is_unique:
                try:
                    await db.redirect_chains.drop_index(index_name)
                    dropped.append(index_name)
                    logger.info(f"✓ Dropped unique index: {index_name}")
                except Exception as e:
                    logger.warning(f"Could not drop index {index_name}: {e}")
        
        if dropped:
            logger.info(f"Successfully removed {len(dropped)} unique index(es): {', '.join(dropped)}")
        else:
            logger.info("No unique indexes to remove from redirect_chains")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        # Don't fail startup if migration fails
        return False


async def rollback(db):
    """Rollback is not needed - we're just removing indexes"""
    pass
