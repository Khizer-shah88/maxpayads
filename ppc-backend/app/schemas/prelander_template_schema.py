"""
Pydantic schemas for Prelander Templates.

A Prelander Template defines the visual/content design for a landing page
(the /d/{slug} page users see before reaching the final offer). Templates are
separate from Landing Pages (which define the domain + campaign binding) and
from Redirection Domains (which define the domain routing infrastructure).
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal

TemplateOs = Literal["windows", "mac", "both"]
TemplateStatus = Literal["active", "paused", "archived"]


class PrlanderTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    os_type: TemplateOs = "both"
    status: TemplateStatus = "active"
    # Visual customisation
    title: str = "Your file is ready to download"
    subtitle: str = "Your file is prepared. Copy the link to download."
    button_text: str = "Copy"
    # Content
    show_password_field: bool = True
    show_video: bool = False
    video_url: Optional[str] = None
    # Tags for organisation
    tags: List[str] = Field(default_factory=list)
    # Internal notes
    notes: Optional[str] = None
    # Full source code template (optional)
    full_html_template: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: List[str]) -> List[str]:
        return [t.strip().lower() for t in (v or []) if t and t.strip()]


class PrlanderTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    os_type: Optional[TemplateOs] = None
    status: Optional[TemplateStatus] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    button_text: Optional[str] = None
    show_password_field: Optional[bool] = None
    show_video: Optional[bool] = None
    video_url: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    # Full source code template (optional)
    full_html_template: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        return [t.strip().lower() for t in v if t and t.strip()]
