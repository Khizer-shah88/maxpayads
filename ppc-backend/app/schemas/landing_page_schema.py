from pydantic import BaseModel, Field, field_validator
from typing import Optional


def _validate_url(v: str) -> str:
    v = (v or "").strip()
    if not v:
        raise ValueError("lander_url is required")
    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError("lander_url must start with http:// or https://")
    return v


def _validate_status(v: str) -> str:
    v = (v or "active").strip().lower()
    if v not in ("active", "paused"):
        raise ValueError("status must be 'active' or 'paused'")
    return v


class LandingPageCreate(BaseModel):
    name: str
    lander_url: str
    campaign_id: Optional[str] = None
    offer_url: Optional[str] = None
    status: str = "active"
    weight: int = Field(default=50, ge=1, le=100)
    # Prelander infrastructure bindings (Domain Glossary):
    # - prelander_domain: hostname of the Prelander redirection domain serving this page
    # - prelander_template_id: specific template; empty/None → OS Default Template
    prelander_domain: Optional[str] = None
    prelander_template_id: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("name is required")
        return v

    @field_validator("lander_url")
    @classmethod
    def _url(cls, v: str) -> str:
        return _validate_url(v)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        return _validate_status(v)


class LandingPageUpdate(BaseModel):
    name: Optional[str] = None
    lander_url: Optional[str] = None
    campaign_id: Optional[str] = None
    offer_url: Optional[str] = None
    status: Optional[str] = None
    weight: Optional[int] = Field(default=None, ge=1, le=100)
    prelander_domain: Optional[str] = None
    prelander_template_id: Optional[str] = None

    @field_validator("lander_url")
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
