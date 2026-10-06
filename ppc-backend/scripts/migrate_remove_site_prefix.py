"""
Remove SITE_ prefix from existing website public_ids in database.

This updates all websites that have public_ids starting with SITE_
to remove the prefix, making URLs cleaner.

Example: SITE_Quf3dmPV → Quf3dmPV

Run: python scripts/migrate_remove_site_prefix.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings


async def migrate_remove_site_prefix():
    """Remove SITE_ prefix from all website public_ids."""
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]
    
    try:
        # Find all websites with SITE_ prefix
        cursor = db.websites.find({"public_id": {"$regex": "^SITE_"}})
        websites = await cursor.to_list(length=None)
        
        total = len(websites)
        
        if total == 0:
            print("✅ No websites with SITE_ prefix found!")
            return
        
        print(f"Found {total} websites with SITE_ prefix")
        print("Removing SITE_ prefix...\n")
        
        updated = 0
        
        for website in websites:
            old_id = website["public_id"]
            new_id = old_id.replace("SITE_", "")
            
            try:
                # Update the website
                await db.websites.update_one(
                    {"_id": website["_id"]},
                    {"$set": {"public_id": new_id}}
                )
                
                print(f"  ✓ {website['domain']}: {old_id} → {new_id}")
                updated += 1
                
            except Exception as e:
                print(f"  ❌ Failed to update {website['domain']}: {e}")
        
        print(f"\n✅ Updated {updated}/{total} websites")
        print("\n⚠️  Important: Existing smartlinks with SITE_ will still work")
        print("   (backward compatibility is maintained in resolve_website_id)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(migrate_remove_site_prefix())
