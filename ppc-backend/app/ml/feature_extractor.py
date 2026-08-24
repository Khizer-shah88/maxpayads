from typing import List
from app.core.constants import COUNTRY_CPC_RATES
from app.utils.ip_utils import is_datacenter_ip
from datetime import datetime


DEVICE_ENCODING = {"desktop": 0, "mobile": 1, "tablet": 2}
COUNTRY_RISK = {
    "US": 0.1, "GB": 0.1, "CA": 0.1, "AU": 0.1, "DE": 0.1,
    "IN": 0.4, "PK": 0.6, "BD": 0.6, "NG": 0.7, "VN": 0.5,
    "DEFAULT": 0.5,
}


def extract_features(click_data: dict) -> List[float]:
    """
    Extract numerical features from click data for ML fraud detection.
    Returns a fixed-length feature vector.
    """
    ip = click_data.get("ip_address", "")
    country_code = click_data.get("country_code") or "DEFAULT"
    device_type = click_data.get("device_type", "desktop")
    user_agent = click_data.get("user_agent", "")
    timestamp = click_data.get("timestamp")

    if isinstance(timestamp, datetime):
        hour_of_day = timestamp.hour
        day_of_week = timestamp.weekday()
    else:
        now = datetime.utcnow()
        hour_of_day = now.hour
        day_of_week = now.weekday()

    features = [
        # Feature 1: Hour of day (0-23) normalized
        hour_of_day / 23.0,
        # Feature 2: Day of week (0-6) normalized
        day_of_week / 6.0,
        # Feature 3: Device type encoded
        DEVICE_ENCODING.get(device_type, 0) / 2.0,
        # Feature 4: Country risk score
        COUNTRY_RISK.get(country_code, COUNTRY_RISK["DEFAULT"]),
        # Feature 5: Known datacenter IP
        1.0 if is_datacenter_ip(ip) else 0.0,
        # Feature 6: User agent length (normalized)
        min(len(user_agent) / 500.0, 1.0),
        # Feature 7: Has referrer
        1.0 if click_data.get("referrer") else 0.0,
        # Feature 8: Request suspicion heuristic (UA length < 50 = suspicious bot)
        1.0 if len(user_agent) < 50 else 0.0,
    ]
    return features
