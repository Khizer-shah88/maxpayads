from datetime import datetime
from typing import Optional
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)


def _oid(id_str: str):
    try:
        return ObjectId(id_str)
    except Exception:
        return id_str


def calculate_earnings(cpc: float, revenue_share: float) -> float:
    """Calculate publisher earnings: earnings = CPC * revenue_share"""
    return round(cpc * revenue_share, 6)


async def update_publisher_balance(publisher_id: str, cpc: float, earnings: float, db):
    """Update publisher balance, earnings, and click counts after valid click."""
    try:
        result = await db.publishers.update_one(
            {"_id": _oid(publisher_id)},
            {
                "$inc": {
                    "balance": earnings,
                    "total_earnings": earnings,
                    "total_clicks": 1,
                    "valid_clicks": 1,
                },
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
        if result.matched_count == 0:
            await db.publishers.update_one(
                {"_id": publisher_id},
                {
                    "$inc": {
                        "balance": earnings,
                        "total_earnings": earnings,
                        "total_clicks": 1,
                        "valid_clicks": 1,
                    },
                    "$set": {"updated_at": datetime.utcnow()},
                },
            )
    except Exception as e:
        logger.error(f"Failed to update publisher balance {publisher_id}: {e}")


async def update_publisher_invalid_click(publisher_id: str, db):
    """Increment invalid click counter for publisher."""
    result = await db.publishers.update_one(
        {"_id": _oid(publisher_id)},
        {
            "$inc": {"total_clicks": 1, "invalid_clicks": 1},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )
    if result.matched_count == 0:
        await db.publishers.update_one(
            {"_id": publisher_id},
            {
                "$inc": {"total_clicks": 1, "invalid_clicks": 1},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )


async def update_website_stats(website_id: str, earnings: float, valid: bool, db):
    """Update website click stats."""
    if not website_id:
        return
    inc_data = {"total_clicks": 1}
    if valid:
        inc_data["valid_clicks"] = 1
        inc_data["total_earnings"] = earnings
    else:
        inc_data["invalid_clicks"] = 1

    result = await db.websites.update_one(
        {"_id": _oid(website_id)},
        {"$inc": inc_data, "$set": {"updated_at": datetime.utcnow()}},
    )
    if result.matched_count == 0:
        await db.websites.update_one(
            {"_id": website_id},
            {"$inc": inc_data, "$set": {"updated_at": datetime.utcnow()}},
        )


async def adjust_publisher_balance(publisher_id: str, amount: float, db):
    """Manually adjust publisher balance (admin only)."""
    result = await db.publishers.update_one(
        {"_id": _oid(publisher_id)},
        {
            "$inc": {"balance": amount},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )
    if result.matched_count == 0:
        await db.publishers.update_one(
            {"_id": publisher_id},
            {
                "$inc": {"balance": amount},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )


async def deduct_withdrawal_amount(publisher_id: str, amount: float, db):
    """Deduct withdrawal amount from publisher balance."""
    result = await db.publishers.update_one(
        {"_id": _oid(publisher_id)},
        {
            "$inc": {"balance": -amount},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )
    if result.matched_count == 0:
        await db.publishers.update_one(
            {"_id": publisher_id},
            {
                "$inc": {"balance": -amount},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
