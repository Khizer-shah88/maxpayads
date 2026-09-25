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
    DEFAULT_CPC: float = 0.0
    DEFAULT_REVENUE_SHARE: float = 1.0

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Withdrawal
    MIN_WITHDRAWAL_AMOUNT: float = 10.0

    # Redirection domains — public IP for DNS verification (A record target)
    SERVER_PUBLIC_IP: str = ""
    PORTAL_HOSTNAMES: str = "maxpayads.com,www.maxpayads.com,vertexmonetize.com,www.vertexmonetize.com,localhost"
    # Redirection / Entry
    ENTRY_FALLBACK_URL: str = "https://www.google.com/"
    ALLOWED_ENTRY_DOMAINS: str = ""
    ENTRY_SESSION_TTL: int = 900
    ENTRY_SESSION_SECRET: str = ""

    # Prelander signed redirect tokens (HMAC-SHA256 in prelander_service)
    REDIRECT_SECRET_KEY: str = ""

    # Prelander authorization session lifetime (seconds). The click-time
    # authorization that grants access to protected prelander content lives
    # this long — default 300s (5 minutes) per the security spec. Overridable
    # per deployment via env: PRELANDER_SESSION_TTL=300
    PRELANDER_SESSION_TTL: int = 300

    # One-time cross-domain handoff validity (seconds) — the token exchanged
    # on the prelander domain for a browsing-session cookie. Short by design.
    PRELANDER_HANDOFF_TTL: int = 60

    # Legacy options retained so existing environment files continue to parse.
    # Denials now always show the session-unavailable message (HTTP 403).
    PRELANDER_DENIED_MODE: str = "generic_page"
    PRELANDER_DENIED_FALLBACK_URL: str = ""

    # STEP 12 — IP-usage policy for prelander authorization. IP is an
    # anti-abuse SIGNAL, never the sole identifier (NAT/VPN/mobile rotation).
    #   relaxed - User-Agent is the browser binding; an IP change falls back
    #             to the slug-index path (default — mobile/VPN safe)
    #   strict  - full (IP+UA) fingerprint must match; rotated IPs are denied
    PRELANDER_IP_MODE: str = "relaxed"

    # STEP 13 — cookie attribute configuration (HttpOnly is always enforced;
    # Secure/SameSite are deployment-relevant, hence configurable). Defaults
    # match production reality: TLS everywhere + Lax so the /click redirect
    # and the /_auth bootstrap keep carrying the cookies.
    PRELANDER_COOKIE_SECURE: bool = True
    PRELANDER_COOKIE_SAMESITE: str = "lax"

    # STEP 15 — tighter rate limit on the prelander auth token surfaces
    # (/prelander/handoff mint + /prelander/_auth exchange). These are the
    # endpoints a token brute-forcer would hammer; the value applies per IP
    # per window, on top of the global request limiter.
    PRELANDER_AUTH_RATE_LIMIT: int = 30
    PRELANDER_AUTH_RATE_WINDOW: int = 60
    # Smartlink signing — strict mode rejects Smartlinks WITHOUT a valid
    # HMAC token at /click. Default false: legacy links (no token) keep
    # working; links CARRYING a token are always verified regardless.
    SMARTLINK_HASH_REQUIRED: bool = False
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
