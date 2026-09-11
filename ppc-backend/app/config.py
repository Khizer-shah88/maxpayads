from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Max Pay Ads"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # JWT
    SECRET_KEY: str = "changeme"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    DB_NAME: str = "ppc_network"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Celery
    CELERY_BROKER_URL: str = "amqp://guest:guest@localhost:5672//"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Admin seed
    ADMIN_EMAIL: str = "admin@maxpayads.com"
    ADMIN_PASSWORD: str = "Admin@123456"
    ADMIN_NAME: str = "Super Admin"

    # GeoIP
    GEOIP_DB_PATH: str = "./GeoLite2-Country.mmdb"

    # CPC defaults
    DEFAULT_CPC: float = 0.05
    DEFAULT_REVENUE_SHARE: float = 0.80

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Withdrawal
    MIN_WITHDRAWAL_AMOUNT: float = 10.0

    # Redirection domains — public IP for DNS verification (A record target)
    SERVER_PUBLIC_IP: str = ""
    # Redirection / Entry
    ENTRY_FALLBACK_URL: str = "https://www.google.com/"
    ALLOWED_ENTRY_DOMAINS: str = ""
    ENTRY_SESSION_TTL: int = 900
    ENTRY_SESSION_SECRET: str = ""

    # Prelander signed redirect tokens (HMAC-SHA256 in prelander_service)
    REDIRECT_SECRET_KEY: str = ""

    # Redirect pipeline tracing — store each click's stage-by-stage resolution
    # trace on the click document so a redirect can be explained after the fact.
    # Turn off to keep click documents minimal on very high volume.
    REDIRECT_TRACE_ENABLED: bool = True

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    model_config = {"env_file": ".env", "case_sensitive": True}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
