from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from bson import ObjectId


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, schema):
        schema.update(type="string")
        return schema


class Publisher(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    public_id: Optional[str] = None  # Unique public ID (e.g., "PUB_ABC12XYZ")
    name: str
    email: str
    password_hash: str
    role: str = "publisher"  # "publisher" or "admin"
    status: str = "pending"  # pending, active, suspended
    revenue_share: float = 0.80
    custom_cpc: Optional[float] = None
    balance: float = 0.0
    total_earnings: float = 0.0
    total_clicks: int = 0
    valid_clicks: int = 0
    invalid_clicks: int = 0
    payment_method: Optional[str] = None
    payment_details: Optional[str] = None
    is_admin_created: bool = False  # True if created by admin, False if self-registered
    created_by: Optional[str] = None  # Admin ID who created this publisher (if is_admin_created=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
