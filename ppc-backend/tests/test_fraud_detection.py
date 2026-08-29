import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_bot_ua_detection():
    """Bot user agents should be detected as fraud."""
    from app.services.fraud_service import check_fraud

    mock_db = MagicMock()
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=0)
    mock_redis.setex = AsyncMock()

    click_data = {
        "publisher_id": "pub1",
        "ip_address": "1.2.3.4",
        "user_agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "country_code": "US",
        "device_type": "desktop",
    }
    is_fraud, reason, score = await check_fraud(click_data, mock_db, mock_redis)
    assert is_fraud is True
    assert reason == "bot_user_agent"


@pytest.mark.asyncio
async def test_datacenter_ip_detection():
    """Datacenter IPs should be flagged as fraud."""
    from app.services.fraud_service import check_fraud

    mock_db = MagicMock()
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=0)
    mock_redis.setex = AsyncMock()

    click_data = {
        "publisher_id": "pub1",
        "ip_address": "34.100.0.1",  # Google Cloud IP
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "country_code": "US",
        "device_type": "desktop",
    }
    is_fraud, reason, score = await check_fraud(click_data, mock_db, mock_redis)
    assert is_fraud is True
    assert reason == "datacenter_ip"


@pytest.mark.asyncio
async def test_rate_limit_detection():
    """IPs exceeding rate limit should be flagged."""
    from app.services.fraud_service import check_fraud

    mock_db = MagicMock()
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=999)  # Way over limit
    mock_redis.expire = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=0)
    mock_redis.setex = AsyncMock()

    click_data = {
        "publisher_id": "pub1",
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "country_code": "US",
        "device_type": "desktop",
    }
    is_fraud, reason, score = await check_fraud(click_data, mock_db, mock_redis)
    assert is_fraud is True
    assert reason == "rate_limit_exceeded"


def test_feature_extractor():
    """Feature extractor should return correct length vector."""
    from app.ml.feature_extractor import extract_features
    from datetime import datetime

    click_data = {
        "ip_address": "1.2.3.4",
        "country_code": "US",
        "device_type": "desktop",
        "user_agent": "Mozilla/5.0",
        "referrer": "https://example.com",
        "cpc": 0.05,
        "timestamp": datetime.utcnow(),
    }
    features = extract_features(click_data)
    assert len(features) == 8
    assert all(0.0 <= f <= 1.0 for f in features)
