from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from datetime import datetime


class GeoRuleCreate(BaseModel):
    country_code: str
    offer_url: str
    priority: int = 0


class GeoRuleResponse(BaseModel):
    id: str
    campaign_id: str
    country_code: str
    offer_url: str
    priority: int
    created_at: datetime


class DeviceRuleCreate(BaseModel):
    device_type: str  # desktop, mobile, tablet
    os: Optional[str] = None
    lander_url: Optional[str] = None
    offer_url: str
    priority: int = 0


class DeviceRuleResponse(BaseModel):
    id: str
    campaign_id: str
    device_type: str
    os: Optional[str]
    lander_url: Optional[str]
    offer_url: str
    priority: int
    created_at: datetime


class CampaignCreate(BaseModel):
    name: str
    default_offer_url: str
    password: Optional[str] = None
    device_os: Optional[str] = None
    direct_redirect_mode: bool = False
    referrer_suppression: bool = False
    rotation_weight: int = 100
    description: Optional[str] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    default_offer_url: Optional[str] = None
    password: Optional[str] = None
    device_os: Optional[str] = None
    status: Optional[str] = None
    direct_redirect_mode: Optional[bool] = None
    referrer_suppression: Optional[bool] = None
    rotation_weight: Optional[int] = None
    description: Optional[str] = None


class CampaignResponse(BaseModel):
    id: str
    name: str
    status: str
    default_offer_url: str
    password: Optional[str] = None
    device_os: Optional[str] = None
    direct_redirect_mode: bool
    referrer_suppression: bool
    rotation_weight: int
    description: Optional[str]
    geo_rules: List[GeoRuleResponse] = []
    device_rules: List[DeviceRuleResponse] = []
    created_at: datetime
    updated_at: datetime


class CountryRuleItem(BaseModel):
    country_code: str
    offer_url: str
    password: str = ""


class DeviceCampaignSave(BaseModel):
    offer_url: str
    password: str = ""
    countries: List[str] = []
    country_rules: List[CountryRuleItem] = []
    direct_redirect_mode: bool = False
    referrer_suppression: bool = False


class AssignCampaignRequest(BaseModel):
    website_id: str
    campaign_id: Optional[str] = None  # None to unassign
