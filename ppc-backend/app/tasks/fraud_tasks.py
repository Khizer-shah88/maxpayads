from app.tasks.celery_app import celery_app
import asyncio
import logging

logger = logging.getLogger(__name__)


@celery_app.task
def reanalyze_suspicious_clicks(hours: int = 24):
    """Batch reanalysis of unprocessed or suspicious clicks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_reanalyze_async(hours))
    loop.close()


async def _reanalyze_async(hours: int):
    from motor.motor_asyncio import AsyncIOMotorClient
    import redis.asyncio as aioredis
    from app.config import settings
    from datetime import datetime, timedelta

    mongo_client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = mongo_client[settings.DB_NAME]

    since = datetime.utcnow() - timedelta(hours=hours)
    cursor = db.clicks.find({
        "status": "pending",
        "timestamp": {"$gte": since}
    })
    clicks = await cursor.to_list(length=1000)
    logger.info(f"Reanalyzing {len(clicks)} pending clicks")

    for click in clicks:
        click_id = str(click["_id"])
        from app.tasks.click_tasks import process_click
        process_click.delay(click_id, {
            k: str(v) if hasattr(v, '__str__') else v
            for k, v in click.items()
            if k != "_id"
        })

    mongo_client.close()
