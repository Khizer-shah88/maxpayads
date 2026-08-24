import json
from typing import Optional, Any
from app.core.constants import SETTINGS_CACHE_PREFIX, SETTINGS_CACHE_TTL
import logging

logger = logging.getLogger(__name__)


async def get_cached_setting(redis, key: str) -> Optional[Any]:
    try:
        data = await redis.get(f"{SETTINGS_CACHE_PREFIX}{key}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Settings cache read error: {e}")
    return None


async def set_cached_setting(redis, key: str, value: Any):
    try:
        await redis.setex(
            f"{SETTINGS_CACHE_PREFIX}{key}",
            SETTINGS_CACHE_TTL,
            json.dumps(value, default=str),
        )
    except Exception as e:
        logger.warning(f"Settings cache write error: {e}")


async def invalidate_setting(redis, key: str):
    try:
        await redis.delete(f"{SETTINGS_CACHE_PREFIX}{key}")
    except Exception as e:
        logger.warning(f"Settings cache invalidation error: {e}")
