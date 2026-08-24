from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from app.services.earnings_service import deduct_withdrawal_amount
from app.config import settings
import logging

logger = logging.getLogger(__name__)


async def create_withdrawal_request(publisher_id: str, publisher_name: str, data: dict, db) -> str:
    """Create a new withdrawal request after validating balance."""
    amount = data["amount"]
    if amount < settings.MIN_WITHDRAWAL_AMOUNT:
        raise ValueError(f"Minimum withdrawal amount is ${settings.MIN_WITHDRAWAL_AMOUNT}")

    try:
        publisher = await db.publishers.find_one({"_id": ObjectId(publisher_id)})
    except Exception:
        publisher = await db.publishers.find_one({"_id": publisher_id})
    if not publisher:
        raise ValueError("Publisher not found")

    balance = publisher.get("balance", 0.0)
    if amount > balance:
        raise ValueError(f"Insufficient balance. Available: ${balance:.2f}")

    # Deduct balance immediately on request
    await deduct_withdrawal_amount(publisher_id, amount, db)

    withdrawal = {
        "publisher_id": publisher_id,
        "publisher_name": publisher_name,
        "amount": amount,
        "payment_method": data["payment_method"],
        "payment_details": data["payment_details"],
        "status": "pending",
        "balance_deducted": True,
        "transaction_id": None,
        "admin_note": None,
        "requested_at": datetime.utcnow(),
        "processed_at": None,
    }
    result = await db.withdrawals.insert_one(withdrawal)
    return str(result.inserted_id)


async def get_publisher_withdrawals(publisher_id: str, db) -> List[dict]:
    cursor = db.withdrawals.find({"publisher_id": publisher_id}).sort("requested_at", -1)
    withdrawals = await cursor.to_list(length=None)
    for w in withdrawals:
        w["id"] = str(w.pop("_id"))
    return withdrawals


async def get_all_withdrawals(db, status: Optional[str] = None, skip: int = 0, limit: int = 50) -> List[dict]:
    query = {}
    if status:
        query["status"] = status
    cursor = db.withdrawals.find(query).skip(skip).limit(limit).sort("requested_at", -1)
    withdrawals = await cursor.to_list(length=None)
    for w in withdrawals:
        w["id"] = str(w.pop("_id"))
    return withdrawals


async def delete_withdrawal(withdrawal_id: str, db) -> bool:
    """Delete a withdrawal record."""
    try:
        wid = ObjectId(withdrawal_id)
    except Exception:
        wid = withdrawal_id
    result = await db.withdrawals.delete_one({"_id": wid})
    return result.deleted_count > 0


async def process_withdrawal(withdrawal_id: str, action: str, transaction_id: Optional[str], admin_note: Optional[str], db) -> bool:
    """Process withdrawal - approve, reject, or mark as paid."""
    try:
        withdrawal = await db.withdrawals.find_one({"_id": ObjectId(withdrawal_id)})
    except Exception:
        withdrawal = await db.withdrawals.find_one({"_id": withdrawal_id})
    if not withdrawal:
        raise ValueError("Withdrawal not found")

    status_map = {
        "approve": "approved",
        "reject": "rejected",
        "paid": "paid",
    }
    new_status = status_map.get(action)
    if not new_status:
        raise ValueError("Invalid action")

    update_data = {
        "status": new_status,
        "admin_note": admin_note,
        "processed_at": datetime.utcnow(),
    }
    if transaction_id:
        update_data["transaction_id"] = transaction_id

    # If rejecting/declining, refund the balance back to publisher
    if action == "reject" and withdrawal.get("balance_deducted"):
        # Refund: add the amount back
        try:
            pid = ObjectId(withdrawal["publisher_id"])
        except Exception:
            pid = withdrawal["publisher_id"]
        await db.publishers.update_one(
            {"_id": pid},
            {"$inc": {"balance": withdrawal["amount"]}, "$set": {"updated_at": datetime.utcnow()}},
        )
        # Try string fallback
        if not await db.publishers.find_one({"_id": pid}):
            await db.publishers.update_one(
                {"_id": withdrawal["publisher_id"]},
                {"$inc": {"balance": withdrawal["amount"]}, "$set": {"updated_at": datetime.utcnow()}},
            )
        update_data["balance_deducted"] = False

    try:
        wid = ObjectId(withdrawal_id)
    except Exception:
        wid = withdrawal_id
    result = await db.withdrawals.update_one(
        {"_id": wid}, {"$set": update_data}
    )
    return result.modified_count > 0
