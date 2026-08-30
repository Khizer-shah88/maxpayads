from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from app.config import settings
import logging

logger = logging.getLogger(__name__)

client: AsyncIOMotorClient = None
db = None

def _init_db_handles():
    """Initialize Mongo client/db handles if they are not ready yet."""
    global client, db

    if client is None or db is None:
        client = AsyncIOMotorClient(settings.MONGODB_URL)
        db = client[settings.DB_NAME]

async def connect_db():
    _init_db_handles()
    await create_indexes()
    try:
        from app.services.domain_service import migrate_legacy_domains
        await migrate_legacy_domains(db)
    except Exception as e:
        logger.warning("Legacy domain migration skipped: %s", e)
    logger.info("Connected to MongoDB")

async def disconnect_db():
    global client, db

    if client:
        client.close()
        client = None
        db = None
        logger.info("Disconnected from MongoDB")


async def create_indexes():
    # Publishers
    await db.publishers.create_index("email", unique=True)
    await db.publishers.create_index("status")
    await db.publishers.create_index("role")

    # Websites
    await db.websites.create_index("publisher_id")
    await db.websites.create_index("domain")

    # Campaigns
    await db.campaigns.create_index("status")
    await db.campaigns.create_index([("created_at", DESCENDING)])

    # Clicks
    await db.clicks.create_index("publisher_id")
    await db.clicks.create_index([("timestamp", DESCENDING)])
    await db.clicks.create_index("ip_address")
    await db.clicks.create_index("is_valid")
    await db.clicks.create_index("campaign_id")
    await db.clicks.create_index("status")
    await db.clicks.create_index([("publisher_id", ASCENDING), ("timestamp", DESCENDING)])
    await db.clicks.create_index([("ip_address", ASCENDING), ("publisher_id", ASCENDING), ("timestamp", DESCENDING)])

    # Withdrawals
    await db.withdrawals.create_index("publisher_id")
    await db.withdrawals.create_index("status")
    await db.withdrawals.create_index([("requested_at", DESCENDING)])

    # Fraud logs
    await db.fraud_logs.create_index("click_id")
    await db.fraud_logs.create_index("publisher_id")
    await db.fraud_logs.create_index([("detected_at", DESCENDING)])

    # Geo rules
    await db.geo_rules.create_index("campaign_id")
    await db.geo_rules.create_index([("campaign_id", ASCENDING), ("country_code", ASCENDING)])

    # Device rules
    await db.device_rules.create_index("campaign_id")

    # System settings
    await db.system_settings.create_index("key", unique=True)

    # Redirection domains
    await db.redirection_domains.create_index([("domain", ASCENDING), ("domain_type", ASCENDING)], unique=True)
    await db.redirection_domains.create_index("domain_type")
    await db.redirection_domains.create_index("publisher_ids")
    await db.redirection_domains.create_index([("domain_type", ASCENDING), ("is_default", DESCENDING)])

    # Prelander templates
    await db.prelander_templates.create_index("status")
    await db.prelander_templates.create_index("os_type")
    await db.prelander_templates.create_index([("created_at", DESCENDING)])

    # Direct links
    await db.direct_links.create_index("slug", unique=True)
    await db.direct_links.create_index("publisher_id")
    await db.direct_links.create_index("campaign_id")
    await db.direct_links.create_index("status")
    await db.direct_links.create_index([("created_at", DESCENDING)])

    # Direct link events (conversions)
    await db.direct_link_events.create_index("link_id")
    await db.direct_link_events.create_index("publisher_id")
    await db.direct_link_events.create_index("slug")
    await db.direct_link_events.create_index([("created_at", DESCENDING)])
    await db.direct_link_events.create_index([("link_id", ASCENDING), ("created_at", DESCENDING)])

    # Template analytics
    await db.template_analytics.create_index([("template_id", ASCENDING), ("date", ASCENDING)], unique=True)
    await db.template_analytics.create_index("template_id")
    await db.template_analytics.create_index("date")
    await db.template_analytics.create_index([("template_id", ASCENDING), ("date", DESCENDING)])

    # Redirect chains
    await db.redirect_chains.create_index("entry_domain", unique=True)
    await db.redirect_chains.create_index("status")
    await db.redirect_chains.create_index("created_by")
    await db.redirect_chains.create_index([("created_at", DESCENDING)])

    # Redirect chain executions
    await db.redirect_chain_executions.create_index("chain_id")
    await db.redirect_chain_executions.create_index("execution_id")
    await db.redirect_chain_executions.create_index("status")
    await db.redirect_chain_executions.create_index([("started_at", DESCENDING)])
    await db.redirect_chain_executions.create_index([("chain_id", ASCENDING), ("started_at", DESCENDING)])

    logger.info("Database indexes created")


def get_database():
    _init_db_handles()
    return db
