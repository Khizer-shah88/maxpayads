"""
Publisher deletion removes EVERY attributed statistic.

Regression tests for the reported bug: after deleting a publisher's records,
the clicks kept showing on the publisher/Direct Link Stats pages because the
old sweep only deleted clicks/withdrawals/fraud_logs and left the direct-link
counters, tracked events, manual conversions and whitelabel profiles behind.
"""
from types import SimpleNamespace

import pytest

from app.services.publisher_service import (
    delete_publisher_and_records,
    delete_publisher_stats_only,
)


class FakeResult:
    def __init__(self, deleted_count=0, matched_count=0, modified_count=0, inserted_id=None):
        self.deleted_count = deleted_count
        self.matched_count = matched_count
        self.modified_count = modified_count
        self.inserted_id = inserted_id


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length=None):
        return list(self._docs)


class Collection:
    """
    Minimal async Mongo collection fake: records every executed operation name
    + query, answers all of them (delete_many → 3, update_many/one → matched).
    """

    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.calls: list = []

    def _record(self, op, *args):
        self.calls.append((op, *args))

    async def delete_many(self, query):
        self._record("delete_many", query)
        return FakeResult(deleted_count=3)

    async def delete_one(self, query):
        self._record("delete_one", query)
        return FakeResult(deleted_count=1)

    async def update_many(self, query, update):
        self._record("update_many", query, update)
        return FakeResult(matched_count=1, modified_count=1)

    async def update_one(self, query, update):
        self._record("update_one", query, update)
        return FakeResult(matched_count=1, modified_count=1)

    def find(self, query=None, *a, **kw):
        self._record("find", query or {})
        return _Cursor(self.docs)


STATS_COLLECTIONS = (
    "clicks", "withdrawals", "fraud_logs", "websites",
    "direct_links", "direct_link_events", "direct_link_manual_conversions",
    "conversion_overrides",
    "stats_profiles",
    "stats_profile_clicks", "stats_profile_impressions",
    "stats_profile_conversions", "stats_profile_manual_conversions",
)


def stats_db(publisher_doc=None):
    """Fake DB with every stats collection present and recordable."""
    names = (*STATS_COLLECTIONS, "redirection_domains", "publishers")
    db = SimpleNamespace(**{name: Collection() for name in names})
    db.publishers.docs = [publisher_doc] if publisher_doc else []
    db.stats_profiles.docs = [
        {"_id": "profile-1", "slug": "prof1", "publisher_id": "64f01e00"},
    ]
    return db


@pytest.mark.asyncio
async def test_delete_and_records_sweeps_every_stats_collection():
    """Full publisher deletion also empties the direct-link and profile stats."""
    db = stats_db()

    deleted = await delete_publisher_and_records("64f01e0000000000000000aa", db)

    assert deleted is True
    swept = {name for name in STATS_COLLECTIONS if getattr(db, name).calls}
    missing = [name for name in STATS_COLLECTIONS if name not in swept]
    assert missing == [], f"deletion skipped these stats collections: {missing}"

    # Domain assignment was cleaned with $pull (membership gone, domain kept).
    red_updates = [update for op, _, update in db.redirection_domains.calls if op == "update_many"]
    assert any(
        update == {"$pull": {"publisher_ids": "64f01e0000000000000000aa"}}
        for update in red_updates
    ), "publisher membership was not pulled from redirection_domains"

    # The publisher document itself was deleted.
    assert any(op == "delete_one" for op, *_ in db.publishers.calls)


@pytest.mark.asyncio
async def test_stats_only_delete_resets_embedded_counters_and_sweeps_events():
    """delete_publisher_stats_only empties link/event/profile data AND resets the
    publisher's embedded click counters (the numbers the publishers page shows)."""
    db = stats_db(publisher_doc={"_id": "64f01e0000000000000000bb", "name": "n"})

    result = await delete_publisher_stats_only("64f01e0000000000000000bb", db)

    # Direct-link counters/events/manual conversions were cleared too.
    for name in (
        "direct_links", "direct_link_events", "direct_link_manual_conversions",
        "conversion_overrides", "stats_profiles",
    ):
        assert getattr(db, name).calls, f"{name} was not swept by stats-only delete"

    # The publishers page counters were reset to zero.
    pub_updates = [update for op, _, update in db.publishers.calls if op == "update_one"]
    assert pub_updates, "embedded publisher counters were not reset"
    assert pub_updates[0]["$set"]["total_clicks"] == 0
    assert pub_updates[0]["$set"]["balance"] == 0.0

    # Reported counts name every surface so the toast can be specific.
    assert result["clicks_deleted"] == 3
    assert result["links_deleted"] == 3
    assert result["profiles_deleted"] == 3