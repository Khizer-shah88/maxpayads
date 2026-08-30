"""
Background Celery tasks for processing clicks asynchronously.
These tasks are pushed to RabbitMQ queue and executed by Celery workers.
"""
from app.tasks.celery_app import celery_app
import asyncio
import logging

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def process_click(self, click_id: str, click_data: dict):
    """
    Process a click in the background:
    1. Run full fraud detection (ML model)
    2. If valid: calculate CPC, earnings, update publisher balance
    3. If fraud: log fraud, mark click invalid
    Note: Basic rule-based fraud was already checked inline at click time.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_process_click_async(click_id, click_data))
        loop.close()
    except Exception as exc:
        logger.error(f"Click processing failed for {click_id}: {exc}")
        raise self.retry(exc=exc, countdown=5)


async def _process_click_async(click_id: str, click_data: dict):
    """Async implementation of click processing."""
    from motor.motor_asyncio import AsyncIOMotorClient
    import redis.asyncio as aioredis
    from bson import ObjectId
    from app.config import settings
    from app.services.fraud_service import check_fraud, log_fraud
    from app.services.cpc_engine import calculate_cpc
    from app.services.earnings_service import (
        calculate_earnings,
        update_publisher_balance,
        update_publisher_invalid_click,
        update_website_stats,
    )
    from datetime import datetime

    mongo_client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = mongo_client[settings.DB_NAME]
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    # Convert click_id string to ObjectId for MongoDB queries
    try:
        oid = ObjectId(click_id)
    except Exception:
        oid = click_id

    try:
        # Skip if already processed as fraud by inline check (from passed data)
        if click_data.get("status") == "invalid" and click_data.get("processed"):
            logger.info(f"Click {click_id} already processed as fraud inline")
            return

        # Re-read click from DB to catch race conditions (e.g. inline check marked
        # it invalid/duplicate after this task was queued)
        db_click = await db.clicks.find_one({"_id": oid})
        if db_click and db_click.get("status") == "invalid":
            logger.info(f"Click {click_id} already marked invalid in DB, skipping")
            return
        if db_click and db_click.get("processed"):
            logger.info(f"Click {click_id} already processed in DB, skipping")
            return

        # Run full fraud detection (includes ML model)
        is_fraud, reason, fraud_score = await check_fraud(click_data, db, redis_client)

        if is_fraud:
            await db.clicks.update_one(
                {"_id": oid},
                {
                    "$set": {
                        "status": "invalid",
                        "is_valid": False,
                        "fraud_reason": reason,
                        "fraud_score": fraud_score,
                        "processed": True,
                        "processed_at": datetime.utcnow(),
                    }
                },
            )
            await log_fraud(click_id, click_data, reason, fraud_score, db)
            await update_publisher_invalid_click(click_data["publisher_id"], db)
            if click_data.get("website_id"):
                await update_website_stats(click_data["website_id"], 0.0, False, db)
            logger.info(f"Click {click_id} marked as fraud: {reason}")
        else:
            # Check if there's a matching offer with custom payout
            offer_payout = None
            try:
                from app.services.traffic_router import find_matching_offer
                click_doc = await db.clicks.find_one({"_id": oid})
                if click_doc:
                    matched_offer = await find_matching_offer(
                        campaign_id=click_doc.get("campaign_id", ""),
                        publisher_id=click_data.get("publisher_id"),
                        website_id=click_data.get("website_id"),
                        os_name=click_data.get("os"),
                        country_code=click_data.get("country_code"),
                        db=db,
                    )
                    if matched_offer and matched_offer.get("payout", 0) > 0:
                        offer_payout = float(matched_offer["payout"])
            except Exception as e:
                logger.debug(f"Offer payout lookup failed: {e}")

            if offer_payout and offer_payout > 0:
                cpc = offer_payout
            else:
                cpc = await calculate_cpc(
                    click_data["publisher_id"],
                    click_data.get("country_code"),
                    click_data.get("device_type"),
                    db,
                )
            # Try ObjectId first (correct for new publishers), fall back to string
            publisher = None
            try:
                publisher = await db.publishers.find_one(
                    {"_id": ObjectId(click_data["publisher_id"])}
                )
            except Exception:
                pass
            if not publisher:
                publisher = await db.publishers.find_one({"_id": click_data["publisher_id"]})
            revenue_share = publisher.get("revenue_share", 0.80) if publisher else 0.80
            earnings = calculate_earnings(cpc, revenue_share)

            await db.clicks.update_one(
                {"_id": oid},
                {
                    "$set": {
                        "status": "valid",
                        "is_valid": True,
                        "fraud_score": fraud_score,
                        "cpc": cpc,
                        "earnings": earnings,
                        "processed": True,
                        "processed_at": datetime.utcnow(),
                    }
                },
            )
            await update_publisher_balance(click_data["publisher_id"], cpc, earnings, db)
            if click_data.get("website_id"):
                await update_website_stats(click_data["website_id"], earnings, True, db)
            logger.info(f"Click {click_id} processed: CPC={cpc}, earnings={earnings}")
    finally:
        mongo_client.close()
        await redis_client.aclose()
