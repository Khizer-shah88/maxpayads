from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class AdminDashboardStats(BaseModel):
    total_clicks: int
    valid_clicks: int
    invalid_clicks: int
    fraud_clicks: int
    total_publishers: int
    active_publishers: int
    pending_publishers: int
    total_earnings: float
    today_clicks: int
    today_valid_clicks: int
    today_earnings: float
    this_month_clicks: int
    this_month_earnings: float
    fraud_rate: float
    pending_withdrawals: int
    pending_withdrawal_amount: float


class PublisherDashboardStats(BaseModel):
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


class TopCountry(BaseModel):
    country_code: str
    country_name: str
    clicks: int
    valid_clicks: int
    earnings: float


class TopPublisher(BaseModel):
    publisher_id: str
    name: str
    email: str
    total_clicks: int
    valid_clicks: int
    total_earnings: float


class ClickTrend(BaseModel):
    date: str
    clicks: int
    valid_clicks: int
    invalid_clicks: int
    earnings: float


class FraudStats(BaseModel):
    total_fraud: int
    fraud_by_reason: dict
    fraud_rate: float
    top_fraud_ips: List[dict]
    today_fraud: int
