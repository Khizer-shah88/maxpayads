from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


def _validate_url(v: str) -> str:
    """Ensure an offer/redirect URL is a well-formed http(s) URL."""
    v = (v or "").strip()
    if not v:
        raise ValueError("offer_url is required")
    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError("offer_url must start with http:// or https://")
    return v


def _validate_status(v: str) -> str:
    v = (v or "active").strip().lower()
    if v not in ("active", "paused"):
        raise ValueError("status must be 'active' or 'paused'")
    return v


class OfferCreate(BaseModel):
    name: str
    offer_url: str
    password: str = ""
    status: str = "active"
    payout: float = Field(default=0.0, ge=0)
    campaign_id: Optional[str] = None
    publisher_ids: List[str] = []   # empty = all publishers
    website_ids: List[str] = []     # empty = all websites
    os_types: List[str] = []        # empty = all OS (windows, mac, android)
    country_codes: List[str] = []   # empty = all countries
    direct_redirect_mode: bool = False

    _ALLOWED_OS = frozenset({"windows", "mac", "android"})

    @field_validator("os_types")
    @classmethod
    def _os_types(cls, v: List[str]) -> List[str]:
        cleaned = []
        for item in v or []:
            key = (item or "").strip().lower()
            if key and key in cls._ALLOWED_OS and key not in cleaned:
                cleaned.append(key)
        return cleaned

    @field_validator("country_codes")
    @classmethod
    def _country_codes(cls, v: List[str]) -> List[str]:
        return [c.strip().upper() for c in (v or []) if c and c.strip()]

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("name is required")
        return v

    @field_validator("offer_url")
    @classmethod
    def _url(cls, v: str) -> str:
        return _validate_url(v)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        return _validate_status(v)


class OfferUpdate(BaseModel):
    name: Optional[str] = None
    offer_url: Optional[str] = None
    password: Optional[str] = None
    status: Optional[str] = None
    payout: Optional[float] = Field(default=None, ge=0)
    campaign_id: Optional[str] = None
    publisher_ids: Optional[List[str]] = None
    website_ids: Optional[List[str]] = None
    os_types: Optional[List[str]] = None
    country_codes: Optional[List[str]] = None
    direct_redirect_mode: Optional[bool] = None

    _ALLOWED_OS = OfferCreate._ALLOWED_OS

    @field_validator("os_types")
    @classmethod
    def _os_types(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        cleaned = []
        for item in v:
            key = (item or "").strip().lower()
            if key and key in cls._ALLOWED_OS and key not in cleaned:
                cleaned.append(key)
        return cleaned

    @field_validator("country_codes")
    @classmethod
    def _country_codes(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        return [c.strip().upper() for c in v if c and c.strip()]

    @field_validator("offer_url")
    @classmethod
    def _url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_url(v)

    @field_validator("status")
    @classmethod
    def _status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_status(v)
