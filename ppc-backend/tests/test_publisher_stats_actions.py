"""Publisher stats actions work before a manual/registered publisher has traffic."""
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pymongo.errors import DuplicateKeyError

from app.dependencies import get_current_admin, get_db
from app.routers import direct_link_router, direct_link_stats_router, public_stats_router


def matches(doc, query):
    for key, value in query.items():
        actual = doc.get(key)
        if isinstance(value, dict):
            for op, operand in value.items():
                if op == "$in" and actual not in operand:
                    return False
                if op == "$gte" and (actual is None or actual < operand):
                    return False
                if op == "$lte" and (actual is None or actual > operand):
                    return False
        elif actual != value:
            return False
    return True


class Cursor:
    def __init__(self, docs):
        self.docs = deepcopy(docs)

    def sort(self, key, direction=None):
        fields = [(key, direction)] if isinstance(key, str) else key
        for name, order in reversed(fields):
            self.docs.sort(key=lambda d: d.get(name, datetime.min), reverse=order == -1)
        return self

    async def to_list(self, length=None):
        return self.docs[:length]

    async def __aiter__(self):
        for doc in self.docs:
            yield doc


class Collection:
    def __init__(self, docs=()):
        self.docs = list(docs)

    def find(self, query, *args):
        return Cursor([d for d in self.docs if matches(d, query)])

    async def find_one(self, query, sort=None):
        cursor = self.find(query)
        if sort:
            cursor.sort(sort)
        return cursor.docs[0] if cursor.docs else None

    async def insert_one(self, doc):
        stored = deepcopy(doc)
        stored.setdefault("_id", ObjectId())
        self.docs.append(stored)
        return SimpleNamespace(inserted_id=stored["_id"])

    async def update_one(self, query, update):
        for doc in self.docs:
            if matches(doc, query):
                doc.update(deepcopy(update.get("$set", {})))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    async def find_one_and_update(self, query, update, upsert=False, **kwargs):
        if not await self.find_one(query) and upsert:
            await self.insert_one({**query, **update.get("$setOnInsert", {})})
        await self.update_one(query, update)
        return await self.find_one(query)

    async def delete_one(self, query):
        doc = next((d for d in self.docs if matches(d, query)), None)
        if doc:
            self.docs.remove(doc)
        return SimpleNamespace(deleted_count=int(doc is not None))

    async def count_documents(self, query):
        return len(self.find(query).docs)

    def aggregate(self, pipeline):
        # These scenarios intentionally have no tracked traffic.
        assert not self.docs
        return Cursor([])


@pytest.fixture
def stats_db():
    return SimpleNamespace(**{name: Collection() for name in (
        "publishers", "direct_links", "stats_profiles", "system_settings", "clicks",
        "direct_link_events", "direct_link_manual_conversions", "conversion_overrides",
    )})


def stats_app(db):
    app = FastAPI()
    # Match production registration order: literal routes before /{link_id}.
    app.include_router(direct_link_stats_router.router)
    app.include_router(direct_link_router.router)
    app.include_router(public_stats_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_admin] = lambda: {"id": "admin", "role": "admin"}
    return app


@pytest.mark.parametrize("publisher_type", ["manual", "registered"])
async def test_new_publisher_all_stats_actions(stats_db, publisher_type):
    pub = {"_id": ObjectId(), "name": "New publisher", "role": "publisher",
           "status": "active", "publisher_type": publisher_type, "public_id": "PUB_NEW123"}
    stats_db.publishers.docs.append(pub)
    pid = str(pub["_id"])
    async with AsyncClient(transport=ASGITransport(app=stats_app(stats_db)), base_url="https://admin.example") as client:
        # Sharing is also supported before any settings modal has been opened.
        initial = await client.post("/direct-links/generate-stats-token", json={"publisher_id": pid})
        assert initial.status_code == 200
        original_share = initial.json()["share_id"]
        setup = await client.post(f"/direct-links/publisher/{pid}/stats-link")
        assert setup.status_code == 200
        link = setup.json()["link"]
        lid = link["id"]
        assert link["masked_url"] == ""
        assert link["status"] == "paused"
        assert len(stats_db.direct_links.docs) == 1

        # Preferences and dedicated domain persist on the very same record.
        prefs = {"show_mac_clicks": True, "show_invalid_clicks": True}
        saved = await client.put(f"/direct-links/{lid}", json={"preferences": prefs, "stats_domain": "stats.example"})
        assert saved.status_code == 200
        reopened = await client.post(f"/direct-links/publisher/{pid}/stats-link")
        assert reopened.json()["link"]["preferences"] == prefs
        assert reopened.json()["link"]["stats_domain"] == "stats.example"
        shared = await client.post(f"/direct-links/{lid}/share-stats-link")
        assert shared.json()["stats_url"] == f"https://stats.example/public-stats/{original_share}"

        # The conversion history route must not be swallowed by /{link_id}.
        history = await client.get("/direct-links/manual-conversions", params={"publisher_id": pid})
        assert history.status_code == 200
        assert history.json()["conversions"] == []
        created = await client.post("/direct-links/manual-conversions", json={
            "publisher_id": pid, "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "conversions": 3, "reason": "External conversions",
        })
        assert created.status_code == 201
        cid = created.json()["conversion"]["id"]
        edited = await client.put(f"/direct-links/manual-conversions/{cid}", json={"conversions": 7, "reason": "Corrected count"})
        assert edited.status_code == 200
        public = await client.get(f"/public-stats/{original_share}")
        assert public.status_code == 200
        assert public.json()["data"]["total_conversions"] == 7
        assert public.json()["data"]["preferences"]["show_mac_clicks"] is True

        regenerated = await client.post(f"/direct-links/{lid}/regenerate-stats-link")
        assert regenerated.status_code == 200
        new_share = regenerated.json()["share_id"]
        assert new_share != original_share
        assert regenerated.json()["stats_url"] == f"https://stats.example/public-stats/{new_share}"
        assert (await client.get(f"/public-stats/{original_share}")).status_code == 410
        report = (await client.get(f"/public-stats/{new_share}")).json()["data"]
        assert report["total_conversions"] == 7
        assert report["preferences"]["show_mac_clicks"] is True

        deleted = await client.delete(f"/direct-links/manual-conversions/{cid}")
        assert deleted.status_code == 200
        assert (await client.get(f"/public-stats/{new_share}")).json()["data"]["total_conversions"] == 0
        assert len(stats_db.direct_links.docs) == 1


async def test_existing_publisher_uses_newest_active_or_paused_link(stats_db):
    pid = ObjectId()
    stats_db.publishers.docs.append({"_id": pid, "role": "publisher", "status": "active"})
    now = datetime.utcnow()
    for age, status in [(0, "archived"), (1, "paused"), (2, "active")]:
        stats_db.direct_links.docs.append({
            "_id": ObjectId(), "publisher_id": str(pid), "status": status,
            "created_at": now - timedelta(days=age), "stats_share_id": f"existing-{age}",
            "preferences": {"show_mac_clicks": True}, "stats_domain": "existing.example",
        })
    before = deepcopy(stats_db.direct_links.docs)
    resolved = await direct_link_router._ensure_publisher_stats_link(str(pid), stats_db)
    assert resolved["_id"] == before[1]["_id"]
    assert stats_db.direct_links.docs == before


async def test_archived_stats_setup_keeps_settings_without_reviving_old_url(stats_db):
    pid = ObjectId()
    stats_db.publishers.docs.append({"_id": pid, "role": "publisher", "status": "active"})
    original = await direct_link_router._ensure_publisher_stats_link(str(pid), stats_db)
    stats_db.direct_links.docs[0].update(status="archived", stats_domain="kept.example")
    reopened = await direct_link_router._ensure_publisher_stats_link(str(pid), stats_db)
    assert reopened["_id"] == original["_id"]
    assert reopened["stats_share_id"] != original["stats_share_id"]
    assert reopened["stats_domain"] == "kept.example"
    assert reopened["status"] == "paused"


async def test_concurrent_setup_reuses_the_winning_record(stats_db, monkeypatch):
    pid = ObjectId()
    stats_db.publishers.docs.append({"_id": pid, "role": "publisher", "status": "active"})
    upsert = stats_db.direct_links.find_one_and_update

    async def competing_insert(query, update, **kwargs):
        await upsert(query, update, **kwargs)
        raise DuplicateKeyError("Concurrent stats setup already inserted this slug")

    monkeypatch.setattr(stats_db.direct_links, "find_one_and_update", AsyncMock(side_effect=competing_insert))
    resolved = await direct_link_router._ensure_publisher_stats_link(str(pid), stats_db)
    assert resolved["_id"] == stats_db.direct_links.docs[0]["_id"]
    assert len(stats_db.direct_links.docs) == 1


@pytest.mark.parametrize("case, expected", [("invalid", 400), ("missing", 404), ("banned", 403), ("removed", 403), ("admin", 404)])
async def test_stats_setup_rejects_unavailable_publishers(stats_db, case, expected):
    pid = ObjectId()
    if case not in ("invalid", "missing"):
        stats_db.publishers.docs.append({"_id": pid, "role": "admin" if case == "admin" else "publisher", "status": case})
    async with AsyncClient(transport=ASGITransport(app=stats_app(stats_db)), base_url="http://test") as client:
        response = await client.post(f"/direct-links/publisher/{'invalid' if case == 'invalid' else pid}/stats-link")
    assert response.status_code == expected
    assert stats_db.direct_links.docs == []
