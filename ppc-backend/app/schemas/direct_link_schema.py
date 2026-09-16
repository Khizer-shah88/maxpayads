"""
Pydantic schemas for Direct Links (masked, hashed-slug affiliate links).

A Direct Link is a short URL of the form:
    https://masked-domain.com/#/a8f9z2

The hash-based slug prevents end-users from identifying the affiliate network
or bypassing the referral structure via direct sign-ups.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal

DirectLinkStatus = Literal["active", "paused", "archived"]


class DirectLinkCreate(BaseModel):
    name: str
    publisher_id: str
    campaign_id: Optional[str] = None
    # The masked domain to use as the base URL (e.g. my-domain.com) - optional
    masked_domain: Optional[str] = None
    # The destination URL after the slug resolves - optional
    destination_url: Optional[str] = None
    # Optional: pin to a specific prelander template
    prelander_template_id: Optional[str] = None
    status: DirectLinkStatus = "active"
    notes: Optional[str] = None
    # Daily conversion cap (0 = unlimited)
    daily_conversion_cap: int = Field(default=0, ge=0)
    # Stats page preferences (what to show/hide to the publisher)
    preferences: Optional[dict] = None
    # Optional PER-PUBLISHER white-label stats domain for this link's share URL
    # (overrides the global stats domain). Bare hostname, no protocol.
    stats_domain: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        return v

    @field_validator("destination_url")
    @classmethod
    def _dest_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("destination_url must start with http:// or https://")
        return v

    @field_validator("masked_domain")
    @classmethod
    def _domain(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower().rstrip("/")
        if not v:
            return None
        # Strip protocol if supplied
        for proto in ("https://", "http://"):
            if v.startswith(proto):
                v = v[len(proto):]
        return v


class DirectLinkUpdate(BaseModel):
    name: Optional[str] = None
    masked_domain: Optional[str] = None
    destination_url: Optional[str] = None
    prelander_template_id: Optional[str] = None
    campaign_id: Optional[str] = None
    status: Optional[DirectLinkStatus] = None
    notes: Optional[str] = None
    daily_conversion_cap: Optional[int] = Field(default=None, ge=0)
    # Stats page preferences (what to show/hide to the publisher) — editable
    # after creation from the admin Direct Link Stats page.
    preferences: Optional[dict] = None
    # Optional PER-PUBLISHER white-label stats domain (e.g. fisherhub.com).
    # When set it overrides the global stats domain for this link's share URL.
    stats_domain: Optional[str] = None

    @field_validator("destination_url")
    @classmethod
    def _dest_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("destination_url must start with http:// or https://")
        return v
