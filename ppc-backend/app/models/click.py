from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Click(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    publisher_id: str
    website_id: Optional[str] = None
    campaign_id: Optional[str] = None
    ip_address: str
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    device_type: str = "desktop"  # desktop, mobile, tablet
    os: Optional[str] = None
    browser: Optional[str] = None
    user_agent: str = ""
    referrer: Optional[str] = None
    destination_url: Optional[str] = None
    cpc: float = 0.0
    earnings: float = 0.0
    status: str = "pending"  # pending, valid, invalid
    fraud_reason: Optional[str] = None
    fraud_score: float = 0.0
    is_valid: bool = False
    processed: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None

    model_config = {"populate_by_name": True}
