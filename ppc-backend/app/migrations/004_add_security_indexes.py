"""
Migration 004: Add Security and Fraud Detection Indexes
========================================================

Indexes for security audit logs, fraud detection, and traffic classification.

Collections:
- security_audit_log: Security event tracking
- clicks: Enhanced with traffic_classification field
- ip_blacklist: IP blocking

Run with:
    python -m app.migrations.004_add_security_indexes
"""

from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ppc_platform")


async def upgrade():
    """Apply migration - create indexes."""
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    
    print("Creating security indexes...")
    
    # Security audit log indexes
    await db.security_audit_log.create_index("event_type")
    await db.security_audit_log.create_index("severity")
    await db.security_audit_log.create_index([("created_at", -1)])
    await db.security_audit_log.create_index([
        ("event_type", 1),
        ("created_at", -1)
    ])
    print("✓ Security audit log indexes created")
    
    # Enhanced clicks indexes for fraud detection
    await db.clicks.create_index("traffic_classification")
    await db.clicks.create_index([
        ("fraud_score", -1),
        ("timestamp", -1)
    ])
    await db.clicks.create_index([
        ("traffic_classification", 1),
        ("timestamp", -1)
    ])
    await db.clicks.create_index("fraud_reason")
    print("✓ Enhanced clicks fraud detection indexes created")
    
    # IP blacklist indexes
    await db.ip_blacklist.create_index("ip_address", unique=True)
    await db.ip_blacklist.create_index([("created_at", -1)])
    print("✓ IP blacklist indexes created")
    
    # Fingerprint index for duplicate detection (if not exists)
    try:
        await db.clicks.create_index("fingerprint")
        print("✓ Fingerprint index created")
    except Exception as e:
        print(f"  Fingerprint index already exists or error: {e}")
    
    # Rate limiting support - TTL indexes handled by Redis
    print("✓ Rate limiting uses Redis (no DB indexes needed)")
    
    client.close()
    print("\n✅ Security indexes migration completed successfully")


async def downgrade():
    """Rollback migration - drop indexes."""
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    
    print("Dropping security indexes...")
    
    # Drop security audit log indexes
    try:
        await db.security_audit_log.drop_index("event_type_1")
        await db.security_audit_log.drop_index("severity_1")
        await db.security_audit_log.drop_index("created_at_-1")
        await db.security_audit_log.drop_index("event_type_1_created_at_-1")
        print("✓ Security audit log indexes dropped")
    except Exception as e:
        print(f"  Error dropping security_audit_log indexes: {e}")
    
    # Drop enhanced clicks indexes
    try:
        await db.clicks.drop_index("traffic_classification_1")
        await db.clicks.drop_index("fraud_score_-1_timestamp_-1")
        await db.clicks.drop_index("traffic_classification_1_timestamp_-1")
        await db.clicks.drop_index("fraud_reason_1")
        print("✓ Enhanced clicks indexes dropped")
    except Exception as e:
        print(f"  Error dropping enhanced clicks indexes: {e}")
    
    # Drop IP blacklist indexes
    try:
        await db.ip_blacklist.drop_index("ip_address_1")
        await db.ip_blacklist.drop_index("created_at_-1")
        print("✓ IP blacklist indexes dropped")
    except Exception as e:
        print(f"  Error dropping ip_blacklist indexes: {e}")
    
    client.close()
    print("\n✅ Security indexes rollback completed")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        asyncio.run(downgrade())
    else:
        asyncio.run(upgrade())
