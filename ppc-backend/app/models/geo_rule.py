from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class GeoRule(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    campaign_id: str
    country_code: str  # ISO 2-letter code e.g. "US", "GB"
    offer_url: str
    priority: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}
