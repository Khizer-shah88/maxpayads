from datetime import datetime, timedelta
from typing import Tuple, Optional
from app.core.constants import (
    MAX_CLICKS_PER_IP_PER_MINUTE,
    DUPLICATE_CLICK_WINDOW_SECONDS,
    REDIS_CLICK_RATE_PREFIX,
    REDIS_DUPLICATE_CLICK_PREFIX,
    FRAUD_BOT_UA,
    FRAUD_DATACENTER_IP,
    FRAUD_DUPLICATE_IP,
    FRAUD_RATE_LIMIT,
    FRAUD_ML_MODEL,
    ML_FRAUD_THRESHOLD,
)
from app.utils.ua_parser import is_bot_user_agent
from app.utils.ip_utils import is_datacenter_ip, is_private_ip
import logging

logger = logging.getLogger(__name__)


async def check_fraud(click_data: dict, db, redis, *, exclude_click_id=None) -> Tuple[bool, Optional[str], float]:
    """
    Run all fraud checks on a click.
    Returns: (is_fraud: bool, reason: str | None, fraud_score: float)

    exclude_click_id: id of the click being judged. The background click task
    runs SECONDS after the inline screening registered the per-day duplicate
    key for this very click — Rule 5 reading that same key flagged every
    fresh click as "duplicate_ip" (the reported "all clicks showing as
    invalid"). The key must only ever name a PRIOR click; the judged click
    is excluded via the fingerprint DB check below (which matches prior
    clicks' fingerprints, never its own row).
    """
    ip = click_data.get("ip_address", "")
    publisher_id = click_data.get("publisher_id", "")
    user_agent = click_data.get("user_agent", "")

    # Rule 1: Bot user agent
    if is_bot_user_agent(user_agent):
        return True, FRAUD_BOT_UA, 1.0

    # Rule 2: Private/localhost IP (testing exclusion for local dev)
    # Only block in production
    # if is_private_ip(ip):
    #     return True, "private_ip", 1.0

    # Rule 3: Datacenter IP
    if is_datacenter_ip(ip):
        return True, FRAUD_DATACENTER_IP, 0.95

    # Rule 4: Rate limit - same IP clicking too fast
    is_rate_limited = await check_ip_rate_limit(ip, redis)
    if is_rate_limited:
        return True, FRAUD_RATE_LIMIT, 0.90

    # Rule 5: Duplicate click - same IP + publisher (per calendar day, UTC).
    # Decided ONLY by prior clicks: the Redis key registered for THIS very
    # click must not defeat it. Look up prior clicks THROUGH THE FINGERPRINT
    # DB CHECK, excluding this click's own document. A key read here would be
    # self-referential because the inline stage already set it for this click.
    if exclude_click_id is not None:
        from app.services import fraud_detection_service as _fds

        is_duplicate, _original = await _fds.check_duplicate_click(
            db, ip, publisher_id, click_data.get("campaign_id"),
        )
    else:
        is_duplicate = await check_duplicate_click(ip, publisher_id, redis)
    if is_duplicate:
        return True, FRAUD_DUPLICATE_IP, 0.85

    # Rule 6: ML model check
    fraud_score = await ml_fraud_check(click_data)
    if fraud_score >= ML_FRAUD_THRESHOLD:
        return True, FRAUD_ML_MODEL, fraud_score

    return False, None, fraud_score


async def check_ip_rate_limit(ip: str, redis) -> bool:
    """Check if IP has exceeded click rate limit per minute."""
    key = f"{REDIS_CLICK_RATE_PREFIX}{ip}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)  # 1 minute window
        return count > MAX_CLICKS_PER_IP_PER_MINUTE
    except Exception as e:
        logger.warning(f"Redis rate limit check failed: {e}")
        return False


async def check_duplicate_click(ip: str, publisher_id: str, redis) -> bool:
    """
    Check if same IP already clicked this publisher today (per calendar day, UTC).
    Same IP coming tomorrow is valid again — key expires at UTC midnight, not rolling 24h.
    """
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    today = now_utc.strftime("%Y-%m-%d")
    # Expire at end of current UTC day + 1h buffer so a late-night click
    # never blocks the visitor all of the following day.
    seconds_until_midnight = (
        (24 - now_utc.hour) * 3600
        - now_utc.minute * 60
        - now_utc.second
        + 3600
    )
    key = f"{REDIS_DUPLICATE_CLICK_PREFIX}{ip}:{publisher_id}:{today}"
    try:
        exists = await redis.exists(key)
        if not exists:
            await redis.setex(key, seconds_until_midnight, "1")
        return bool(exists)
    except Exception as e:
        logger.warning(f"Redis duplicate check failed: {e}")
        return False


async def ml_fraud_check(click_data: dict) -> float:
    """Run ML model fraud detection. Returns fraud score 0-1."""
    try:
        from app.ml.isolation_forest_model import fraud_model
        from app.ml.feature_extractor import extract_features
        features = extract_features(click_data)
        if fraud_model.model is not None:
            from starlette.concurrency import run_in_threadpool
            return await run_in_threadpool(fraud_model.predict, features)
    except Exception as e:
        logger.warning(f"ML fraud check failed: {e}")
    return 0.0


async def log_fraud(click_id: str, click_data: dict, reason: str, score: float, db):
    """Log fraudulent click to fraud_logs collection."""
    fraud_log = {
        "click_id": click_id,
        "publisher_id": click_data.get("publisher_id"),
        "ip_address": click_data.get("ip_address"),
        "country_code": click_data.get("country_code"),
        "device_type": click_data.get("device_type"),
        "user_agent": click_data.get("user_agent", "")[:500],
        "fraud_reason": reason,
        "fraud_score": score,
        "details": {
            "country": click_data.get("country_name"),
            "browser": click_data.get("browser"),
            "os": click_data.get("os"),
        },
        "detected_at": datetime.utcnow(),
    }
    await db.fraud_logs.insert_one(fraud_log)
