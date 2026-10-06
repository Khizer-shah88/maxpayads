"""
Fix clicks with CPC = 0.0 by recalculating CPC retroactively.

This script finds all clicks where cpc=0.0 but status='valid',
recalculates the correct CPC, and updates them.

Run: python scripts/fix_zero_cpc_clicks.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import sys
import os
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.services.cpc_engine import calculate_cpc


async def fix_zero_cpc_clicks():
    """Find and fix clicks with zero CPC."""
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]
    
    try:
        # Find valid clicks with zero CPC
        cursor = db.clicks.find({
            "status": "valid",
            "cpc": {"$lte": 0.0}
        })
        
        clicks = await cursor.to_list(length=None)
        total = len(clicks)
        
        if total == 0:
            print("✅ No clicks with zero CPC found!")
            return
        
        print(f"Found {total} valid clicks with zero CPC")
        print("Recalculating CPC for each click...\n")
        
        fixed = 0
        failed = 0
        
        for click in clicks:
            try:
                # Recalculate CPC
                cpc = await calculate_cpc(
                    publisher_id=str(click.get("publisher_id", "")),
                    country_code=click.get("country_code"),
                    device_type=click.get("device_type"),
                    db=db
                )
                
                # Get publisher revenue share
                publisher = None
                try:
                    pub_id = click.get("publisher_id")
                    if isinstance(pub_id, str):
                        try:
                            publisher = await db.publishers.find_one({"_id": ObjectId(pub_id)})
                        except:
                            publisher = await db.publishers.find_one({"_id": pub_id})
                except Exception:
                    pass
                
                revenue_share = publisher.get("revenue_share", 1.0) if publisher else 1.0
                earnings = round(cpc * revenue_share, 6)
                
                # Update click
                await db.clicks.update_one(
                    {"_id": click["_id"]},
                    {
                        "$set": {
                            "cpc": cpc,
                            "earnings": earnings,
                            "processed": True,
                            "processed_at": datetime.utcnow()
                        }
                    }
                )
                
                fixed += 1
                if fixed % 100 == 0:
                    print(f"  Fixed {fixed}/{total} clicks...")
                
            except Exception as e:
                failed += 1
                print(f"  ❌ Failed to fix click {click['_id']}: {e}")
        
        print(f"\n✅ Fixed {fixed} clicks")
        if failed > 0:
            print(f"⚠️  Failed to fix {failed} clicks")
        
        # Update publisher balances
        print("\nRecalculating publisher balances...")
        publishers = await db.publishers.find({"role": "publisher"}).to_list(length=None)
        
        for pub in publishers:
            try:
                pub_id = pub["_id"]
                
                # Calculate total earnings from all valid clicks
                pipeline = [
                    {
                        "$match": {
                            "publisher_id": str(pub_id),
                            "status": "valid"
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "total_earnings": {"$sum": "$earnings"}
                        }
                    }
                ]
                
                result = await db.clicks.aggregate(pipeline).to_list(length=1)
                total_earnings = result[0]["total_earnings"] if result else 0.0
                
                # Get total withdrawals
                withdrawals_pipeline = [
                    {
                        "$match": {
                            "publisher_id": str(pub_id),
                            "status": {"$in": ["approved", "completed"]}
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "total_withdrawn": {"$sum": "$amount"}
                        }
                    }
                ]
                
                result = await db.withdrawals.aggregate(withdrawals_pipeline).to_list(length=1)
                total_withdrawn = result[0]["total_withdrawn"] if result else 0.0
                
                # Balance = earnings - withdrawals
                balance = total_earnings - total_withdrawn
                
                # Update publisher
                await db.publishers.update_one(
                    {"_id": pub_id},
                    {
                        "$set": {
                            "balance": balance,
                            "total_earnings": total_earnings
                        }
                    }
                )
                
                print(f"  ✓ {pub.get('name', 'Unknown')}: ${balance:.2f}")
                
            except Exception as e:
                print(f"  ❌ Failed to update publisher {pub.get('name', 'Unknown')}: {e}")
        
        print("\n✅ All done!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(fix_zero_cpc_clicks())
