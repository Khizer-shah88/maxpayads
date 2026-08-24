from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ClickResponse(BaseModel):
    id: str
    publisher_id: str
    website_id: Optional[str]
    campaign_id: Optional[str]
    ip_address: str
    country_code: Optional[str]
    country_name: Optional[str]
    device_type: str
    os: Optional[str]
    browser: Optional[str]
    cpc: float
    earnings: float
    status: str
    fraud_reason: Optional[str]
    fraud_score: float
    is_valid: bool
    timestamp: datetime
    processed_at: Optional[datetime]


class ClickFilterParams(BaseModel):
    publisher_id: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    status: Optional[str] = None
    country_code: Optional[str] = None
    device_type: Optional[str] = None
    page: int = 1
    limit: int = 50
