"""Tiny Redis JSON cache for hot-path per-request lookups.

Every helper here is fail-open: when Redis is unavailable (or caching is
disabled) the loader runs directly, so behaviour degrades to the plain DB
path instead of breaking requests.

Enabled by settings.CLICK_HOT_CACHE (tests force it off via conftest, so
every test keeps reading fresh database state).
"""
import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_NONE = "\x00none"  # negative-cache sentinel: a stored "no result"

# Shared key names — keep in one place so producers/consumers cannot drift.
CAMPAIGNS_SNAPSHOT_KEY = "kv:campsnap"
GLOBAL_FALLBACK_KEY = "kv:gfurl"
STATS_HOST_KEY = "kv:statshost"
STRUCTURES_KEY = "kv:structs"


async def invalidate_domain_routing():
    """Drop routing snapshots after an admin edits a domain or chain.

    Only configuration caches are touched; active click/session tickets stay
    intact. SCAN keeps this admin operation from blocking the Redis server.
    """
    from app.cache.redis_client import get_redis

    redis = get_redis()
    if redis is None:
        return
    try:
        for prefix in ('kv:durl:', 'kv:dpool:', 'kv:drole:', 'kv:chainscan:', 'kv:chainseq:'):
            batch = []
            async for key in redis.scan_iter(match=prefix + '*', count=128):
                batch.append(key)
                if len(batch) == 128:
                    await redis.delete(*batch)
                    batch.clear()
            if batch:
                await redis.delete(*batch)
    except Exception as exc:
        logger.warning('Routing cache invalidation failed; TTL remains in effect: %s', exc)


async def cached_json(redis, key: str, ttl: int, loader):
    """
    Return `loader()` for `key`, memoized in Redis as JSON for `ttl` seconds.

    - `None` results are cached too (negative cache), so recurring misses do
      not stampede the database.
    - Any Redis error falls through to the loader — caching never breaks or
      slows a request beyond one failed GET.
    - A handle without get/setex (None, or an object that is not a redis
      client) also falls through — the hot path must degrade to the DB
      lookup, never raise AttributeError into a 500.
    - Callers namespace their own keys; shared keys live above.
    """
    if redis is None or not settings.CLICK_HOT_CACHE:
        return await loader()
    if not (hasattr(redis, "get") and hasattr(redis, "setex")):
        # Defensive: not a usable redis client — run the loader directly.
        return await loader()
    try:
        raw = await redis.get(key)
        if raw is not None:
            return None if raw == _NONE else json.loads(raw)
    except Exception as e:
        logger.warning("kv read %s failed: %s", key, e)
    value = await loader()
    try:
        await redis.setex(key, ttl, _NONE if value is None else json.dumps(value, default=str))
    except Exception as e:
        logger.warning("kv write %s failed: %s", key, e)
    return value
