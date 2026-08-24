from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class SystemSettings(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    key: str  # unique setting key
    value: Any
    description: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: Optional[str] = None

    model_config = {"populate_by_name": True}
