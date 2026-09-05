"""
Pydantic schemas for Direct Link Stats Profiles
================================================

Stats profiles provide white-label statistics tracking for publishers
with opaque slugs and no leakage of internal information.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from datetime import datetime

ProfileStatus = Literal["active", "paused", "archived"]


class StatsProfilePreferences(BaseModel):
    """Configurable preferences for what stats to show/hide to publishers."""
    show_os: bool = Field(True, description="Show OS breakdown (Windows, Android, iOS, etc.)")
    show_country: bool = Field(True, description="Show country statistics")
    show_device: bool = Field(True, description="Show device type breakdown (Desktop, Mobile, Tablet)")
    show_clicks: bool = Field(True, description="Show total clicks")
    show_unique_clicks: bool = Field(True, description="Show unique clicks")
    show_valid_clicks: bool = Field(True, description="Show validated/unique clicks")
    show_invalid_clicks: bool = Field(False, description="Show invalid/fraud clicks")
    show_impressions: bool = Field(True, description="Show impression count")
    show_conversions: bool = Field(True, description="Show conversion count")
    show_cr: bool = Field(True, description="Show conversion rate")
    show_fraud_score: bool = Field(False, description="Show average fraud score")
    show_daily_breakdown: bool = Field(True, description="Show daily breakdown chart")


class StatsProfileCreate(BaseModel):
    """Create a new stats profile."""
    name: str = Field(..., min_length=2, max_length=100)
    publisher_id: str
    source_name: Optional[str] = None  # External source identifier
    stats_domain: Optional[str] = None  # Custom stats domain
    status: ProfileStatus = "active"
    notes: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    preferences: StatsProfilePreferences = Field(default_factory=StatsProfilePreferences)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v


class StatsProfileUpdate(BaseModel):
    """Update an existing stats profile."""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    source_name: Optional[str] = None
    stats_domain: Optional[str] = None
    status: Optional[ProfileStatus] = None
    notes: Optional[str] = None
    metadata: Optional[dict] = None
    preferences: Optional[StatsProfilePreferences] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v


class ManualConversionCreate(BaseModel):
    """Create a manual conversion override."""
    profile_slug: str
    date: str  # YYYY-MM-DD format
    conversions: int = Field(..., ge=0)
    reason: str = Field(..., min_length=5)
    metadata: dict = Field(default_factory=dict)

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        """Validate date format."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")


class ManualConversionUpdate(BaseModel):
    """Update a manual conversion override."""
    conversions: Optional[int] = Field(None, ge=0)
    reason: Optional[str] = Field(None, min_length=5)
    metadata: Optional[dict] = None


class StatsProfileOut(BaseModel):
    """Stats profile response model."""
    id: str
    slug: str  # 8-char opaque identifier
    name: str
    publisher_id: str
    publisher_name: Optional[str] = None
    source_name: Optional[str] = None
    stats_domain: Optional[str] = None
    stats_url: str  # Full URL to access stats
    status: ProfileStatus
    notes: Optional[str] = None
    metadata: dict
    
    # Statistics
    total_impressions: int = 0
    total_clicks: int = 0
    unique_clicks: int = 0
    valid_clicks: int = 0
    invalid_clicks: int = 0
    total_conversions: int = 0
    
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class StatsDataResponse(BaseModel):
    """Stats data for a profile."""
    profile_slug: str
    date_from: str
    date_to: str
    
    # Aggregated stats
    impressions: int = 0
    clicks: int = 0
    unique_clicks: int = 0
    valid_clicks: int = 0
    invalid_clicks: int = 0
    conversions: int = 0
    
    # OS breakdown
    os_stats: List[dict] = Field(default_factory=list)
    
    # Daily breakdown
    daily_stats: List[dict] = Field(default_factory=list)
    
    # Manual conversions
    manual_conversions: List[dict] = Field(default_factory=list)
