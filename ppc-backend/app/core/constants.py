from typing import Dict

# Click status
CLICK_VALID = "valid"
CLICK_INVALID = "invalid"
CLICK_PENDING = "pending"

# Fraud reasons
FRAUD_DUPLICATE_IP = "duplicate_ip"
FRAUD_BOT_UA = "bot_user_agent"
FRAUD_DATACENTER_IP = "datacenter_ip"
FRAUD_RATE_LIMIT = "rate_limit_exceeded"
FRAUD_ML_MODEL = "ml_anomaly"
FRAUD_SELF_CLICK = "self_click"

# Publisher status
PUB_ACTIVE = "active"
PUB_PENDING = "pending"
PUB_SUSPENDED = "suspended"

# Campaign status
CAMPAIGN_ACTIVE = "active"
CAMPAIGN_PAUSED = "paused"
CAMPAIGN_DELETED = "deleted"

# Withdrawal status
WD_PENDING = "pending"
WD_APPROVED = "approved"
WD_REJECTED = "rejected"
WD_PAID = "paid"

# Device types
DEVICE_DESKTOP = "desktop"
DEVICE_MOBILE = "mobile"
DEVICE_TABLET = "tablet"

# Known datacenter CIDRs (partial representative list)
DATACENTER_CIDRS = [
    # AWS
    "3.0.0.0/8", "13.32.0.0/15", "18.0.0.0/8", "52.0.0.0/8",
    "54.0.0.0/8", "34.192.0.0/10",
    # Google Cloud
    "34.0.0.0/9", "35.0.0.0/8", "104.154.0.0/15",
    # Azure
    "20.0.0.0/8", "40.0.0.0/8", "13.64.0.0/11",
    # DigitalOcean
    "159.89.0.0/16", "167.99.0.0/16", "134.209.0.0/16",
    # Linode
    "45.56.0.0/18", "45.79.0.0/16",
    # Vultr
    "45.32.0.0/15", "66.42.0.0/16",
    # OVH
    "51.68.0.0/16", "54.36.0.0/14",
]

# Bot User Agent keywords (lowercase)
BOT_UA_KEYWORDS = [
    "bot", "crawler", "spider", "scraper", "curl", "wget",
    "python-requests", "python-urllib", "go-http-client", "java/",
    "libwww", "scrapy", "headlesschrome", "phantomjs", "selenium",
    "puppeteer", "playwright", "httpclient", "okhttp", "axios",
    "node-fetch", "got/", "superagent", "aiohttp", "httpx",
]

# Rate limits
MAX_CLICKS_PER_IP_PER_MINUTE: int = 10
MAX_REQUESTS_PER_IP_PER_MINUTE: int = 200
DUPLICATE_CLICK_WINDOW_SECONDS: int = 86400  # 24 hours

# Country CPC rates (USD)
COUNTRY_CPC_RATES: Dict[str, float] = {
    "US": 0.10, "GB": 0.09, "CA": 0.09, "AU": 0.08,
    "DE": 0.08, "FR": 0.07, "NL": 0.07, "SE": 0.07,
    "NO": 0.08, "CH": 0.09, "DK": 0.07, "FI": 0.07,
    "JP": 0.06, "KR": 0.05, "SG": 0.06, "HK": 0.06,
    "NZ": 0.07, "IE": 0.07, "AT": 0.07, "BE": 0.07,
    "IT": 0.05, "ES": 0.05, "PT": 0.04, "PL": 0.04,
    "CZ": 0.04, "HU": 0.03, "RO": 0.03, "GR": 0.04,
    "BR": 0.04, "MX": 0.04, "AR": 0.03, "CL": 0.04,
    "IN": 0.03, "PK": 0.02, "BD": 0.02, "LK": 0.02,
    "NG": 0.02, "ZA": 0.03, "GH": 0.02, "KE": 0.02,
    "EG": 0.02, "MA": 0.02, "TR": 0.03, "IL": 0.06,
    "AE": 0.07, "SA": 0.06, "QA": 0.07, "KW": 0.06,
    "TH": 0.03, "VN": 0.02, "PH": 0.02, "ID": 0.03,
    "MY": 0.04, "RU": 0.03, "UA": 0.02,
    "DEFAULT": 0.03,
}

# Revenue share default
DEFAULT_REVENUE_SHARE: float = 0.80

# Redis key prefixes
REDIS_CLICK_RATE_PREFIX = "click_rate:"
REDIS_REQUEST_RATE_PREFIX = "req_rate:"
REDIS_CAMPAIGN_CACHE_PREFIX = "campaigns:"
REDIS_SETTINGS_CACHE_PREFIX = "settings:"
REDIS_TOKEN_BLACKLIST_PREFIX = "blacklist:"
REDIS_DUPLICATE_CLICK_PREFIX = "dup_click:"

# Aliases for cache modules
CAMPAIGN_CACHE_PREFIX = REDIS_CAMPAIGN_CACHE_PREFIX
SETTINGS_CACHE_PREFIX = REDIS_SETTINGS_CACHE_PREFIX

# Cache TTLs (seconds)
CAMPAIGN_CACHE_TTL = 300   # 5 minutes
SETTINGS_CACHE_TTL = 600   # 10 minutes
DASHBOARD_CACHE_TTL = 60   # 1 minute

# ML fraud threshold
ML_FRAUD_THRESHOLD = 0.65
