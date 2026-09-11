"""
Redirection domain schemas.

Domain Glossary terms (the only spellings used from here on):
    anchor      first redirect domain that receives the Smartlink
    inter       intermediate redirect domain after the Anchor
    prelander   optional page shown before the final Offer

The legacy spellings link/intermediate/last are still accepted on input and
normalized away by `app.core.glossary.normalize_domain_type`.
"""
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.glossary import normalize_domain_type

DomainType = Literal["anchor", "inter", "prelander"]
DomainStatus = Literal["active", "paused"]
DnsStatus = Literal["pending", "verified", "failed"]

# Built-in page template a Prelander domain serves. These are the templates the
# prelander renderer actually implements — "default" follows the visitor's own
# OS, "windows"/"mac" pin the page to that OS regardless of the visitor.
PrelanderTemplateChoice = Literal["default", "windows", "mac"]


def _coerce_domain_type(v: Any) -> Any:
    """Accept canonical or legacy spellings; hand the canonical term to Literal."""
    return normalize_domain_type(v, default=v)


class RedirectionDomainCreate(BaseModel):
    domain: str
    domain_type: DomainType
    publisher_ids: List[str] = Field(default_factory=list)
    is_default: bool = False
    status: DomainStatus = "active"
    template: PrelanderTemplateChoice = "default"
    template_id: Optional[str] = None  # Link to prelander_templates collection
    # Weight — relative (not %) number controlling prelander traffic distribution.
    # Only meaningful for prelander-type domains.
    weight: int = Field(default=100, ge=0, le=1_000_000)
    notes: Optional[str] = None

    @field_validator("domain_type", mode="before")
    @classmethod
    def _normalize_domain_type(cls, v: Any) -> Any:
        return _coerce_domain_type(v)


class RedirectionDomainUpdate(BaseModel):
    domain: Optional[str] = None
    publisher_ids: Optional[List[str]] = None
    is_default: Optional[bool] = None
    status: Optional[DomainStatus] = None
    template: Optional[PrelanderTemplateChoice] = None
    template_id: Optional[str] = None
    weight: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    notes: Optional[str] = None


class RedirectionDomainOut(BaseModel):
    id: str
    domain: str
    domain_type: DomainType
    publisher_ids: List[str]
    publisher_names: List[str] = Field(default_factory=list)
    is_default: bool
    status: DomainStatus
    template: PrelanderTemplateChoice
    template_id: Optional[str] = None  # Link to prelander_templates collection
    weight: int = 100
    dns_status: DnsStatus
    dns_checked_at: Optional[str] = None
    resolved_ips: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @field_validator("domain_type", mode="before")
    @classmethod
    def _normalize_domain_type(cls, v: Any) -> Any:
        return _coerce_domain_type(v)
