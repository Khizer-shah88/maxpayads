from app.tasks.celery_app import celery_app
import asyncio
import logging

logger = logging.getLogger(__name__)


@celery_app.task
def compute_daily_analytics():
    """Compute and cache daily analytics aggregations."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_compute_analytics_async())
    loop.close()


async def _compute_analytics_async():
    from motor.motor_asyncio import AsyncIOMotorClient
    import redis.asyncio as aioredis
    import json
    from app.config import settings
    from datetime import datetime

    mongo_client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = mongo_client[settings.DB_NAME]
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    pipeline = [
        {"$match": {"timestamp": {"$gte": today}}},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "valid": {"$sum": {"$cond": ["$is_valid", 1, 0]}},
            "earnings": {"$sum": "$earnings"},
        }}
    ]
    result = await db.clicks.aggregate(pipeline).to_list(length=1)
    stats = result[0] if result else {"total": 0, "valid": 0, "earnings": 0}
    stats.pop("_id", None)

    await redis_client.setex("analytics:today", 300, json.dumps(stats, default=str))
    logger.info(f"Daily analytics computed: {stats}")

    mongo_client.close()
    await redis_client.aclose()
