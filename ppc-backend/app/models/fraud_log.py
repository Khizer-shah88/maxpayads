from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class FraudLog(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    click_id: str
    publisher_id: str
    ip_address: str
    country_code: Optional[str] = None
    device_type: Optional[str] = None
    user_agent: Optional[str] = None
    fraud_reason: str
    fraud_score: float = 0.0
    details: Dict[str, Any] = {}
    detected_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}
