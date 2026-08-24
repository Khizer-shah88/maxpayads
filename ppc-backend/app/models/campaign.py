from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Campaign(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    status: str = "active"  # active, paused, deleted
    default_offer_url: str
    password: Optional[str] = None
    device_os: Optional[str] = None  # windows, mac, android (for device-centric campaigns)
    direct_redirect_mode: bool = False
    referrer_suppression: bool = False
    rotation_weight: int = 100  # percentage for weighted rotation
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}
