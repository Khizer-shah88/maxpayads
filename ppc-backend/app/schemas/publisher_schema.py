from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class PublisherResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    status: str
    revenue_share: float
    custom_cpc: Optional[float]
    balance: float
    total_earnings: float
    total_clicks: int
    valid_clicks: int
    invalid_clicks: int
    payment_method: Optional[str]
    payment_details: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]


class PublisherUpdate(BaseModel):
    name: Optional[str] = None
    payment_method: Optional[str] = None
    payment_details: Optional[str] = None


class AdminPublisherUpdate(BaseModel):
    status: Optional[str] = None
    revenue_share: Optional[float] = None
    custom_cpc: Optional[float] = None


class BalanceAdjustment(BaseModel):
    amount: float  # positive to add, negative to subtract
    reason: Optional[str] = None


class PublisherStats(BaseModel):
    today_clicks: int
    today_earnings: float
    today_valid_clicks: int
    today_invalid_clicks: int
    total_clicks: int
    total_earnings: float
    valid_clicks: int
    invalid_clicks: int
    balance: float
    this_month_clicks: int
    this_month_earnings: float
