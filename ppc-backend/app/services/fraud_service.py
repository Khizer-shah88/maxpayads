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


async def check_fraud(click_data: dict, db, redis) -> Tuple[bool, Optional[str], float]:
    """
    Run all fraud checks on a click.
    Returns: (is_fraud: bool, reason: str | None, fraud_score: float)
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

    # Rule 5: Duplicate click - same IP + publisher within window
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
    """Check if same IP already clicked this publisher recently."""
    key = f"{REDIS_DUPLICATE_CLICK_PREFIX}{ip}:{publisher_id}"
    try:
        exists = await redis.exists(key)
        if not exists:
            await redis.setex(key, DUPLICATE_CLICK_WINDOW_SECONDS, "1")
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
            return fraud_model.predict(features)
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
