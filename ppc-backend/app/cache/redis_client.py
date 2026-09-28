import redis.asyncio as aioredis
from app.config import settings
import logging

logger = logging.getLogger(__name__)

redis_client: aioredis.Redis = None


async def connect_redis():
    global redis_client
    # Floor at 500: 16 workers × many concurrent Redis ops.
    # settings.REDIS_MAX_CONNECTIONS defaults to 64 (per-process config) —
    # way too low for 16 workers. Hard-floor it at 500 so the pool is never
    # the bottleneck even if the env var is not set.
    max_conn = max(getattr(settings, "REDIS_MAX_CONNECTIONS", 64), 500)
    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        max_connections=max_conn,
        retry_on_timeout=True,
        health_check_interval=30,
        socket_keepalive=True,
        socket_keepalive_options={},
    )
    await redis_client.ping()
    logger.info("Connected to Redis (pool=%d)", max_conn)


async def disconnect_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        logger.info("Disconnected from Redis")


def get_redis() -> aioredis.Redis:
    return redis_client
