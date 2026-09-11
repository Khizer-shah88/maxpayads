from app.tasks.celery_app import celery_app
import asyncio
import logging

logger = logging.getLogger(__name__)


@celery_app.task
def recalculate_publisher_earnings(publisher_id: str):
    """Recalculate and sync publisher earnings from click records."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_recalculate_async(publisher_id))
    loop.close()


async def _recalculate_async(publisher_id: str):
    from motor.motor_asyncio import AsyncIOMotorClient
    from app.config import settings
    from datetime import datetime
    from bson import ObjectId

    mongo_client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = mongo_client[settings.DB_NAME]

    pipeline = [
        {"$match": {"publisher_id": publisher_id, "is_valid": True}},
        {"$group": {
            "_id": None,
            "total_earnings": {"$sum": "$earnings"},
            "valid_clicks": {"$sum": 1},
        }}
    ]
    result = await db.clicks.aggregate(pipeline).to_list(length=1)
    if result:
        stats = result[0]
        # Publisher `_id` is an ObjectId, but the task receives it as a
        # string (and legacy docs may hold a string `_id`) — try both shapes,
        # mirroring click_tasks.process_click.
        pub_filter = None
        try:
            pub_filter = {"_id": ObjectId(publisher_id)}
        except Exception:
            pass
        if not await db.publishers.find_one(pub_filter or {"_id": publisher_id}, {"_id": 1}):
            pub_filter = {"_id": publisher_id}
        await db.publishers.update_one(
            pub_filter,
            {"$set": {
                "total_earnings": stats["total_earnings"],
                "valid_clicks": stats["valid_clicks"],
                "updated_at": datetime.utcnow(),
            }}
        )
        logger.info(f"Earnings recalculated for publisher {publisher_id}")

    mongo_client.close()
