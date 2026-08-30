"""
Models for tracking template-specific performance analytics.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class TemplateAnalytics(BaseModel):
    """Daily analytics for a specific prelander template."""
    id: Optional[str] = Field(default=None, alias="_id")
    template_id: str
    date: str  # YYYY-MM-DD format for easy querying
    # Click tracking
    total_clicks: int = 0
    unique_clicks: int = 0
    valid_clicks: int = 0
    invalid_clicks: int = 0
    fraud_clicks: int = 0
    # Conversion tracking
    total_conversions: int = 0
    conversion_rate: float = 0.0
    # Manual CR override capability
    manual_cr_override: Optional[float] = None
    manual_conversions_override: Optional[int] = None
    override_reason: Optional[str] = None
    override_updated_at: Optional[datetime] = None
    override_updated_by: Optional[str] = None  # admin user ID
    # Geographic breakdown
    geo_stats: Dict[str, int] = Field(default_factory=dict)  # {"US": 123, "GB": 45}
    device_stats: Dict[str, int] = Field(default_factory=dict)  # {"desktop": 100, "mobile": 68}
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class TemplatePerformance(BaseModel):
    """Summary performance metrics for a template across date ranges."""
    template_id: str
    template_name: str
    total_clicks: int = 0
    total_conversions: int = 0
    average_cr: float = 0.0
    best_performing_date: Optional[str] = None
    worst_performing_date: Optional[str] = None
    trend_direction: str = "stable"  # "up", "down", "stable"


class ManualCRUpdateRequest(BaseModel):
    """Request to manually override conversion rate/count for a template on a specific date."""
    template_id: str
    date: str  # YYYY-MM-DD
    manual_conversions: Optional[int] = None
    manual_cr: Optional[float] = None
    reason: str

    def __init__(self, **data):
        super().__init__(**data)
        # Ensure at least one override value is provided
        if self.manual_conversions is None and self.manual_cr is None:
            raise ValueError("Either manual_conversions or manual_cr must be provided")