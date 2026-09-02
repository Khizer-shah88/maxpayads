"""Cleanup test data from database."""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def cleanup():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['ppc_platform_test']
    
    # Delete test publishers
    result = await db.publishers.delete_many({'email': {'$regex': '@example\\.com|@test\\.com'}})
    print(f'Deleted {result.deleted_count} test publishers')
    
    # Delete test websites
    result = await db.websites.delete_many({'domain': {'$regex': 'test|example'}})
    print(f'Deleted {result.deleted_count} test websites')
    
    client.close()

if __name__ == '__main__':
    asyncio.run(cleanup())
