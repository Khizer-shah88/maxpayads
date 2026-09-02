from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime

DomainType = Literal["link", "intermediate", "last"]
DomainStatus = Literal["active", "paused"]
DnsStatus = Literal["pending", "verified", "failed"]
LastDomainTemplate = Literal["default", "windows", "mac"]


class RedirectionDomainCreate(BaseModel):
    domain: str
    domain_type: DomainType
    publisher_ids: List[str] = Field(default_factory=list)
    is_default: bool = False
    status: DomainStatus = "active"
    template: LastDomainTemplate = "default"
    template_id: Optional[str] = None  # Link to prelander_templates collection
    notes: Optional[str] = None


class RedirectionDomainUpdate(BaseModel):
    domain: Optional[str] = None
    publisher_ids: Optional[List[str]] = None
    is_default: Optional[bool] = None
    status: Optional[DomainStatus] = None
    template: Optional[LastDomainTemplate] = None
    template_id: Optional[str] = None  # Link to prelander_templates collection
    notes: Optional[str] = None


class RedirectionDomainOut(BaseModel):
    id: str
    domain: str
    domain_type: DomainType
    publisher_ids: List[str]
    publisher_names: List[str] = Field(default_factory=list)
    is_default: bool
    status: DomainStatus
    template: LastDomainTemplate
    template_id: Optional[str] = None  # Link to prelander_templates collection
    dns_status: DnsStatus
    dns_checked_at: Optional[str] = None
    resolved_ips: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
