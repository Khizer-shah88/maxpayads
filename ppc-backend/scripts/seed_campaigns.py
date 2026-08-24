"""
Seed sample campaigns, geo rules, and device rules.
Run: python scripts/seed_campaigns.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings


async def seed_campaigns():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]

    # Campaign 1: Global with geo targeting
    campaign1 = {
        "_id": "campaign_001",
        "name": "Global Campaign - Finance",
        "status": "active",
        "default_offer_url": "https://example-offer.com/finance",
        "direct_redirect_mode": False,
        "referrer_suppression": True,
        "rotation_weight": 60,
        "description": "Finance offer targeting Tier 1 countries",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    # Campaign 2: Direct redirect
    campaign2 = {
        "_id": "campaign_002",
        "name": "Mobile Campaign - Apps",
        "status": "active",
        "default_offer_url": "https://example-offer.com/apps",
        "direct_redirect_mode": True,
        "referrer_suppression": False,
        "rotation_weight": 40,
        "description": "Mobile app install campaign",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    for campaign in [campaign1, campaign2]:
        existing = await db.campaigns.find_one({"_id": campaign["_id"]})
        if not existing:
            await db.campaigns.insert_one(campaign)
            print(f"Created campaign: {campaign['name']}")

    # Geo rules for campaign 1
    geo_rules = [
        {"campaign_id": "campaign_001", "country_code": "US", "offer_url": "https://example-offer.com/finance-us", "priority": 10},
        {"campaign_id": "campaign_001", "country_code": "GB", "offer_url": "https://example-offer.com/finance-gb", "priority": 9},
        {"campaign_id": "campaign_001", "country_code": "CA", "offer_url": "https://example-offer.com/finance-ca", "priority": 9},
        {"campaign_id": "campaign_001", "country_code": "AU", "offer_url": "https://example-offer.com/finance-au", "priority": 8},
        {"campaign_id": "campaign_001", "country_code": "DE", "offer_url": "https://example-offer.com/finance-de", "priority": 8},
    ]
    for rule in geo_rules:
        rule["created_at"] = datetime.utcnow()
        await db.geo_rules.insert_one(rule)
    print(f"Created {len(geo_rules)} geo rules")

    # Device rules for campaign 2
    device_rules = [
        {"campaign_id": "campaign_002", "device_type": "mobile", "os": "Android", "lander_url": "https://example-offer.com/lander-android", "offer_url": "https://example-offer.com/apps-android", "priority": 10},
        {"campaign_id": "campaign_002", "device_type": "mobile", "os": "iOS", "lander_url": "https://example-offer.com/lander-ios", "offer_url": "https://example-offer.com/apps-ios", "priority": 10},
        {"campaign_id": "campaign_002", "device_type": "desktop", "os": "Windows", "lander_url": None, "offer_url": "https://example-offer.com/apps-desktop", "priority": 5},
    ]
    for rule in device_rules:
        rule["created_at"] = datetime.utcnow()
        await db.device_rules.insert_one(rule)
    print(f"Created {len(device_rules)} device rules")

    # Default system settings
    settings_data = [
        {"key": "global_default_offer_url", "value": "https://example.com", "description": "Fallback URL when no campaign matches"},
        {"key": "min_withdrawal_amount", "value": 10.0, "description": "Minimum withdrawal amount in USD"},
        {"key": "max_clicks_per_ip_per_minute", "value": 10, "description": "Rate limit for clicks per IP per minute"},
    ]
    for setting in settings_data:
        setting["updated_at"] = datetime.utcnow()
        await db.system_settings.update_one(
            {"key": setting["key"]}, {"$set": setting}, upsert=True
        )
    print("System settings configured")

    client.close()
    print("Seeding complete!")


if __name__ == "__main__":
    asyncio.run(seed_campaigns())
