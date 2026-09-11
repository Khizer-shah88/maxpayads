"""
Offer schemas.

Glossary: an Offer is an eligibility rule — which Campaign is allowed for which
publisher(s)/website(s)/country/OS — and carries the CPC, a fixed monetary
amount credited per valid click (never a percentage).

`cpc` was previously spelled `payout`; that name is still accepted on input and
still read from pre-migration documents.
"""
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from typing import List, Optional

from app.core.glossary import normalize_os

LEGACY_CPC_KEY = "payout"


def _normalize_os_types(values: Optional[List[str]]) -> Optional[List[str]]:
    """Resolve each entry onto the fixed OS enum, dropping unknown values."""
    if values is None:
        return None
    cleaned: List[str] = []
    for item in values:
        key = normalize_os(item)
        if key and key not in cleaned:
            cleaned.append(key)
    return cleaned


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
    model_config = ConfigDict(populate_by_name=True)

    name: str
    offer_url: str
    password: str = ""
    status: str = "active"
    # CPC — fixed amount credited per valid click.
    cpc: float = Field(
        default=0.0, ge=0,
        validation_alias=AliasChoices("cpc", LEGACY_CPC_KEY),
    )
    campaign_id: Optional[str] = None
    publisher_ids: List[str] = []   # empty = all publishers
    website_ids: List[str] = []     # empty = all websites
    os_types: List[str] = []        # empty = all OS
    country_codes: List[str] = []   # empty = all countries
    direct_redirect_mode: bool = False

    @field_validator("os_types")
    @classmethod
    def _os_types(cls, v: List[str]) -> List[str]:
        return _normalize_os_types(v or [])

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
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = None
    offer_url: Optional[str] = None
    password: Optional[str] = None
    status: Optional[str] = None
    cpc: Optional[float] = Field(
        default=None, ge=0,
        validation_alias=AliasChoices("cpc", LEGACY_CPC_KEY),
    )
    campaign_id: Optional[str] = None
    publisher_ids: Optional[List[str]] = None
    website_ids: Optional[List[str]] = None
    os_types: Optional[List[str]] = None
    country_codes: Optional[List[str]] = None
    direct_redirect_mode: Optional[bool] = None

    @field_validator("os_types")
    @classmethod
    def _os_types(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _normalize_os_types(v)

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
