from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DeviceRule(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    campaign_id: str
    device_type: str  # desktop, mobile, tablet
    os: Optional[str] = None  # Windows, Android, iOS, MacOS, Linux
    lander_url: Optional[str] = None  # intermediate landing page
    offer_url: str
    priority: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}
