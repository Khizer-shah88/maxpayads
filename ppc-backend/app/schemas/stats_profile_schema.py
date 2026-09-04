"""
Stats Profile Schemas for Direct Link Stats

Defines what metrics are visible to publishers in their stats dashboard.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class StatsProfilePreferences(BaseModel):
    """Configurable preferences for what stats to show/hide"""
    show_os: bool = Field(True, description="Show OS breakdown (Windows, Android, iOS, etc.)")
    show_country: bool = Field(True, description="Show country statistics")
    show_device: bool = Field(True, description="Show device type breakdown (Desktop, Mobile, Tablet)")
    show_clicks: bool = Field(True, description="Show total clicks")
    show_valid_clicks: bool = Field(True, description="Show validated/unique clicks")
    show_invalid_clicks: bool = Field(False, description="Show invalid/fraud clicks")
    show_impressions: bool = Field(True, description="Show impression count")
    show_conversions: bool = Field(True, description="Show conversion count")
    show_cr: bool = Field(True, description="Show conversion rate")
    show_fraud_score: bool = Field(False, description="Show average fraud score")


class StatsProfileCreate(BaseModel):
    """Create new stats profile for a publisher"""
    publisher_id: str = Field(..., description="Publisher ID")
    preferences: StatsProfilePreferences = Field(default_factory=StatsProfilePreferences)


class StatsProfileUpdate(BaseModel):
    """Update existing stats profile preferences"""
    preferences: StatsProfilePreferences


class StatsProfileResponse(BaseModel):
    """Stats profile response"""
    id: str
    publisher_id: str
    preferences: StatsProfilePreferences
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ManualConversionCreate(BaseModel):
    """Create manual conversion entry for a specific date"""
    date: str = Field(..., description="Date in YYYY-MM-DD format", regex=r'^\d{4}-\d{2}-\d{2}$')
    publisher_id: str = Field(..., description="Publisher ID")
    link_id: Optional[str] = Field(None, description="Specific link ID (optional, applies to all links if not set)")
    conversions: int = Field(..., ge=0, description="Number of conversions")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for manual entry")


class ManualConversionUpdate(BaseModel):
    """Update existing manual conversion entry"""
    conversions: int = Field(..., ge=0)
    reason: str = Field(..., min_length=1, max_length=500)


class ManualConversionResponse(BaseModel):
    """Manual conversion entry response"""
    id: str
    date: str
    publisher_id: str
    publisher_name: Optional[str] = None
    link_id: Optional[str] = None
    link_name: Optional[str] = None
    conversions: int
    reason: str
    entered_by: str
    entered_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
