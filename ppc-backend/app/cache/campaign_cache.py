import json
from typing import Optional, List
from app.core.constants import CAMPAIGN_CACHE_PREFIX, CAMPAIGN_CACHE_TTL
import logging

logger = logging.getLogger(__name__)

CACHE_KEY = "all_campaigns"


async def get_cached_campaigns(redis) -> Optional[List[dict]]:
    try:
        data = await redis.get(f"{CAMPAIGN_CACHE_PREFIX}{CACHE_KEY}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Campaign cache read error: {e}")
    return None


async def set_cached_campaigns(redis, campaigns: List[dict]):
    try:
        await redis.setex(
            f"{CAMPAIGN_CACHE_PREFIX}{CACHE_KEY}",
            CAMPAIGN_CACHE_TTL,
            json.dumps(campaigns, default=str),
        )
    except Exception as e:
        logger.warning(f"Campaign cache write error: {e}")


async def invalidate_campaign_cache(redis):
    try:
        await redis.delete(f"{CAMPAIGN_CACHE_PREFIX}{CACHE_KEY}")
    except Exception as e:
        logger.warning(f"Campaign cache invalidation error: {e}")
