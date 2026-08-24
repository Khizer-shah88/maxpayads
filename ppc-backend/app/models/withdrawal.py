from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Withdrawal(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    publisher_id: str
    publisher_name: str
    amount: float
    payment_method: str  # paypal, bank_transfer, crypto, usdt
    payment_details: str  # wallet address / account info
    status: str = "pending"  # pending, approved, rejected, paid
    transaction_id: Optional[str] = None
    admin_note: Optional[str] = None
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None

    model_config = {"populate_by_name": True}
