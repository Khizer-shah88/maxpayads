"""
Seed default Smartlink Structures
===================================
Creates the three standard structures from the specification:
1. Standard (pub + site)
2. Tag + SID (tag + sid)
3. Tag Only (tag only)
"""

import asyncio
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import os


async def seed_smartlink_structures():
    """Seed the three default smartlink structures."""
    mongo_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "ppc_network")
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    now = datetime.utcnow()
    
    # Define the three standard structures from the specification
    structures = [
        {
            "name": "Standard",
            "publisher_param": "pub",
            "website_param": "site",
            "include_website": True,
            "extra_params": [],
            "is_default": True,  # Standard is the default
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
        {
            "name": "Tag + SID",
            "publisher_param": "tag",
            "website_param": "sid",
            "include_website": True,
            "extra_params": [],
            "is_default": False,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
        {
            "name": "Tag Only",
            "publisher_param": "tag",
            "website_param": None,
            "include_website": False,
            "extra_params": [],
            "is_default": False,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
    ]
    
    # Check if structures already exist
    existing_count = await db.smartlink_structures.count_documents({})
    
    if existing_count > 0:
        print(f"✓ Smartlink structures already exist ({existing_count} found)")
        client.close()
        return
    
    # Insert the structures
    result = await db.smartlink_structures.insert_many(structures)
    print(f"✓ Seeded {len(result.inserted_ids)} smartlink structures")
    
    # Verify
    for struct in structures:
        print(f"  - {struct['name']}: {struct['publisher_param']}={'{PUBLISHER_ID}'}", end="")
        if struct['include_website'] and struct['website_param']:
            print(f"&{struct['website_param']}={'{SITE_ID}'}")
        else:
            print()
    
    client.close()


if __name__ == "__main__":
    asyncio.run(seed_smartlink_structures())
