from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Website(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    publisher_id: str
    domain: str
    name: str
    status: str = "active"
    assigned_campaign_id: Optional[str] = None
    total_clicks: int = 0
    valid_clicks: int = 0
    invalid_clicks: int = 0
    total_earnings: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}
