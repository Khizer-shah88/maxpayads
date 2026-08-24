import redis.asyncio as aioredis
from app.config import settings
import logging

logger = logging.getLogger(__name__)

redis_client: aioredis.Redis = None


async def connect_redis():
    global redis_client
    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    await redis_client.ping()
    logger.info("Connected to Redis")


async def disconnect_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        logger.info("Disconnected from Redis")


def get_redis() -> aioredis.Redis:
    return redis_client
