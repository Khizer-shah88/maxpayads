"""
Migration 005: Domain Glossary Terminology
==========================================
Date: 2026-09-11
Description: Renames stored values and field names onto the Domain Glossary terms.

Changes:
- redirection_domains.domain_type:  link → anchor, intermediate → inter, last → prelander
- redirect_chains:                  intermediate_domain → inter_domain
                                    pre_lander_pool     → prelander_pool
- redirect_chain_sessions:          intermediate_timestamp → inter_timestamp
- offers:                           payout → cpc   (the amount itself is untouched)

No click, statistic, earning or withdrawal document is read or written by this
migration. Recorded history keeps the values it was recorded with.

The application reads both spellings, so it keeps working before, during and
after this runs; the migration only removes the need for the compatibility path.

Run with:
    python -m app.migrations.005_domain_glossary_terms
    python -m app.migrations.005_domain_glossary_terms downgrade
"""

import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

MIGRATION_VERSION = 5
MIGRATION_NAME = "domain_glossary_terms"

# stored value → glossary term
DOMAIN_TYPE_RENAMES = {
    "link": "anchor",
    "intermediate": "inter",
    "last": "prelander",
}

# collection → {old field: new field}
FIELD_RENAMES = {
    "redirect_chains": {
        "intermediate_domain": "inter_domain",
        "pre_lander_pool": "prelander_pool",
    },
    "redirect_chain_sessions": {
        "intermediate_timestamp": "inter_timestamp",
    },
    "offers": {
        "payout": "cpc",
    },
}


def _connect():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    return client, client[settings.DB_NAME]


async def _check_domain_type_conflicts(db, renames: dict) -> list:
    """
    A domain is unique per (domain, domain_type). If a host already exists under
    both the old and the new spelling, renaming would collide with that unique
    index — report those instead of failing halfway through.
    """
    conflicts = []
    for old, new in renames.items():
        cursor = db.redirection_domains.find({"domain_type": old}, {"domain": 1})
        async for doc in cursor:
            clash = await db.redirection_domains.find_one({
                "domain": doc.get("domain"),
                "domain_type": new,
            })
            if clash:
                conflicts.append((doc.get("domain"), old, new))
    return conflicts


async def _rename_domain_types(db, renames: dict) -> int:
    conflicts = await _check_domain_type_conflicts(db, renames)
    if conflicts:
        print("✗ Cannot rename domain types — these hosts exist under both spellings:")
        for domain, old, new in conflicts:
            print(f"    {domain}: '{old}' and '{new}'")
        print("  Remove the duplicate rows in Admin → Redirection Domains, then re-run.")
        raise RuntimeError("domain_type rename conflicts")

    total = 0
    for old, new in renames.items():
        result = await db.redirection_domains.update_many(
            {"domain_type": old},
            {"$set": {"domain_type": new}},
        )
        if result.modified_count:
            print(f"✓ redirection_domains.domain_type: {old} → {new} ({result.modified_count})")
        total += result.modified_count
    return total


async def _rename_fields(db, collection_name: str, renames: dict) -> int:
    collection = db[collection_name]
    total = 0
    for old, new in renames.items():
        # Only rename where the new name is not already present, so a partially
        # applied run — or a document the app already wrote in the new shape —
        # is never clobbered.
        result = await collection.update_many(
            {old: {"$exists": True}, new: {"$exists": False}},
            {"$rename": {old: new}},
        )
        # Anything left holding both keys has an authoritative new value already;
        # drop the stale duplicate.
        leftovers = await collection.update_many(
            {old: {"$exists": True}, new: {"$exists": True}},
            {"$unset": {old: ""}},
        )
        if result.modified_count or leftovers.modified_count:
            print(
                f"✓ {collection_name}.{old} → {new} "
                f"({result.modified_count} renamed, {leftovers.modified_count} duplicates dropped)"
            )
        total += result.modified_count + leftovers.modified_count
    return total


async def upgrade():
    """Apply the glossary terminology to stored data."""
    client, db = _connect()
    print(f"Migration {MIGRATION_VERSION}: {MIGRATION_NAME} (db: {settings.DB_NAME})")
    try:
        changed = await _rename_domain_types(db, DOMAIN_TYPE_RENAMES)
        for collection_name, renames in FIELD_RENAMES.items():
            changed += await _rename_fields(db, collection_name, renames)
        print(f"\n✅ Domain glossary migration completed ({changed} documents touched)")
    finally:
        client.close()


async def downgrade():
    """Restore the pre-glossary spellings."""
    client, db = _connect()
    print(f"Rolling back migration {MIGRATION_VERSION}: {MIGRATION_NAME}")
    try:
        reverse_types = {new: old for old, new in DOMAIN_TYPE_RENAMES.items()}
        changed = await _rename_domain_types(db, reverse_types)
        for collection_name, renames in FIELD_RENAMES.items():
            reverse_fields = {new: old for old, new in renames.items()}
            changed += await _rename_fields(db, collection_name, reverse_fields)
        print(f"\n✅ Domain glossary rollback completed ({changed} documents touched)")
    finally:
        client.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        asyncio.run(downgrade())
    else:
        asyncio.run(upgrade())
