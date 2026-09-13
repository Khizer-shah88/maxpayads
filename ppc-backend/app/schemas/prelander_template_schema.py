"""
Pydantic schemas for Prelander Templates.

A Prelander Template defines the visual/content design for a landing page
(the /d/{slug} page users see before reaching the final offer). Templates are
separate from Landing Pages (which define the domain + campaign binding) and
from Redirection Domains (which define the domain routing infrastructure).
"""
from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional, List, Literal

from app.core.glossary import normalize_os

# Which OS a template is written for. The values are the fixed OS enum, plus
# "both" — the stored value meaning "any OS", kept because existing templates
# carry it.
TemplateOs = Literal["windows", "android", "mac", "ios", "both"]
TEMPLATE_OS_ANY = "both"
TemplateStatus = Literal["active", "paused", "archived"]


def _coerce_template_os(v: Any) -> Any:
    """Resolve an OS name onto the fixed OS enum; pass "both" (any OS) through."""
    if isinstance(v, str) and v.strip().lower() == TEMPLATE_OS_ANY:
        return TEMPLATE_OS_ANY
    return normalize_os(v, default=v)


class PrlanderTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    os_type: TemplateOs = "both"
    status: TemplateStatus = "active"
    is_default: bool = False
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

    @field_validator("os_type", mode="before")
    @classmethod
    def _os_type(cls, v: Any) -> Any:
        return _coerce_template_os(v)

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
    is_default: Optional[bool] = None
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

    @field_validator("os_type", mode="before")
    @classmethod
    def _os_type(cls, v: Any) -> Any:
        return _coerce_template_os(v) if v is not None else v

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
