"""
Database Migration Runner
==========================
Runs pending database migrations in order.

Usage:
    python scripts/run_migrations.py          # Run all pending migrations
    python scripts/run_migrations.py --down   # Rollback last migration
"""

import asyncio
import sys
import os
import importlib
import logging
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def get_applied_migrations(db):
    """Get list of already applied migrations."""
    cursor = db.migrations.find({}).sort("version", 1)
    applied = await cursor.to_list(length=None)
    return [m["version"] for m in applied]


async def get_available_migrations():
    """Get list of available migration modules."""
    migrations_dir = Path(__file__).parent.parent / "app" / "migrations"
    if not migrations_dir.exists():
        migrations_dir.mkdir(parents=True, exist_ok=True)
        return []
    
    migration_files = sorted([
        f for f in migrations_dir.glob("*.py")
        if f.name != "__init__.py" and not f.name.startswith(".")
    ])
    
    migrations = []
    for f in migration_files:
        # Extract version number from filename (e.g., "002_add_public_publisher_id.py" -> 2)
        try:
            version = int(f.stem.split("_")[0])
            migrations.append({
                "version": version,
                "module_name": f.stem,
                "file_path": f,
            })
        except (IndexError, ValueError):
            logger.warning(f"Skipping invalid migration file: {f.name}")
    
    return sorted(migrations, key=lambda x: x["version"])


async def run_migration(db, migration_info, direction="up"):
    """Run a single migration."""
    logger.info(f"{'Applying' if direction == 'up' else 'Rolling back'} migration {migration_info['version']}: {migration_info['module_name']}")
    
    # Dynamically import the migration module
    module_path = f"app.migrations.{migration_info['module_name']}"
    try:
        migration_module = importlib.import_module(module_path)
    except ImportError as e:
        logger.error(f"Failed to import migration {migration_info['module_name']}: {e}")
        return False
    
    # Run the migration
    try:
        await migration_module.run(db, direction=direction)
        return True
    except Exception as e:
        logger.error(f"Migration {migration_info['version']} failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_up_migrations(db):
    """Run all pending migrations (forward)."""
    logger.info("=== Running Database Migrations ===")
    
    applied = await get_applied_migrations(db)
    available = await get_available_migrations()
    
    logger.info(f"Applied migrations: {applied}")
    logger.info(f"Available migrations: {[m['version'] for m in available]}")
    
    pending = [m for m in available if m["version"] not in applied]
    
    if not pending:
        logger.info("✓ No pending migrations")
        return True
    
    logger.info(f"Found {len(pending)} pending migration(s)")
    
    for migration in pending:
        success = await run_migration(db, migration, direction="up")
        if not success:
            logger.error(f"❌ Migration {migration['version']} failed. Stopping.")
            return False
    
    logger.info("✓ All migrations applied successfully")
    return True


async def run_down_migration(db):
    """Rollback the last applied migration."""
    logger.info("=== Rolling Back Last Migration ===")
    
    applied = await get_applied_migrations(db)
    available = await get_available_migrations()
    
    if not applied:
        logger.info("No migrations to roll back")
        return True
    
    last_version = applied[-1]
    migration_info = next((m for m in available if m["version"] == last_version), None)
    
    if not migration_info:
        logger.error(f"Migration file for version {last_version} not found!")
        return False
    
    success = await run_migration(db, migration_info, direction="down")
    if success:
        logger.info(f"✓ Migration {last_version} rolled back successfully")
    else:
        logger.error(f"❌ Rollback of migration {last_version} failed")
    
    return success


async def main():
    """Main migration runner."""
    # Parse command line args
    direction = "up"
    if len(sys.argv) > 1 and sys.argv[1] == "--down":
        direction = "down"
    
    # Connect to database
    logger.info(f"Connecting to MongoDB: {settings.MONGODB_URL}")
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]
    
    try:
        # Test connection
        await db.command("ping")
        logger.info("✓ Database connection successful")
        
        # Run migrations
        if direction == "up":
            success = await run_up_migrations(db)
        else:
            success = await run_down_migration(db)
        
        if success:
            logger.info("=== Migration Complete ===")
            sys.exit(0)
        else:
            logger.error("=== Migration Failed ===")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()
        logger.info("Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
