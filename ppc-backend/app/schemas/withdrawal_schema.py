from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class WithdrawalRequest(BaseModel):
    amount: float
    payment_method: str  # paypal, bank_transfer, crypto, usdt
    payment_details: str

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be positive")
        return round(v, 2)

    @field_validator("payment_method")
    @classmethod
    def validate_method(cls, v):
        allowed = ["paypal", "bank_transfer", "crypto", "usdt", "binance_pay"]
        if v not in allowed:
            raise ValueError(f"Payment method must be one of: {', '.join(allowed)}")
        return v


class WithdrawalResponse(BaseModel):
    id: str
    publisher_id: str
    publisher_name: str
    amount: float
    payment_method: str
    payment_details: str
    status: str
    transaction_id: Optional[str]
    admin_note: Optional[str]
    requested_at: datetime
    processed_at: Optional[datetime]


class WithdrawalAction(BaseModel):
    action: str  # approve, reject, paid
    transaction_id: Optional[str] = None
    admin_note: Optional[str] = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v):
        allowed = ["approve", "reject", "paid"]
        if v not in allowed:
            raise ValueError(f"Action must be one of: {', '.join(allowed)}")
        return v
