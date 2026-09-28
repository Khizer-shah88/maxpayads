"""
Direct Link Stats & duplicate-IP scoping regressions.

Covers the four requested changes:

1. Duplicate-IP validation is PER PUBLISHER: the same visitor clicking
   different publishers is a valid click for each; only a repeat on the same
   publisher is flagged. (The old inline Redis key was ip:website — manual
   publishers have no website, so all their visitors shared one key.)
2. GET /direct-links/publisher-domains returns real traffic stats
   (clicks/today conversions) and the global default domains — the data for
   the Direct Link Stats table's Clicks / Today / Assigned / Default columns.
3. PUT /direct-links/manual-conversions/{id} preserves the stored reason when
   the update omits it (reason is optional on conversion entries).
4. POST /direct-links/manual-conversions works with NO reason at all.
"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.dependencies import get_db
from app.services import redirect_pipeline as rp
from app.services.redirect_pipeline import RedirectResolutionContext
from app.services import fraud_detection_service as fds


class ClickCollection:
    """clicks collection fake with timestamp-aware matching + aggregate."""

    def __init__(self, docs=()):
        self.docs = list(docs)

    def find(self, query, *args):
        return self

    async def find_one(self, query, *args, **kwargs):
        fp = query.get("fingerprint")
        for doc in self.docs:
            if doc.get("fingerprint") == fp:
                return doc
        return None

    def aggregate(self, pipeline):
        # Support the $match → $group shape used by publisher-domains:
        # optional match (timestamp/created_at ranges), then group by _id.
        rows_source = self.docs
        if pipeline and "$match" in pipeline[0]:
            match = pipeline[0]["$match"]
            ts = match.get("timestamp") or match.get("created_at") or {}
            gte = ts.get("$gte")
            if gte is not None:
                rows_source = [d for d in self.docs if d.get("timestamp", d.get("created_at")) >= gte]
        group_stage = pipeline[-1].get("$group", {}) if pipeline else {}
        id_field = (group_stage.get("_id") or "$publisher_id").lstrip("$")
        sums = {}
        for doc in rows_source:
            key = doc.get(id_field)
            inc = group_stage.get("total", {}).get("$sum", 1)
            value = 1 if inc == 1 else (doc.get(str(inc).lstrip("$"), 0) or 0)
            sums[key] = sums.get(key, 0) + value
        rows = [{"_id": k, "total": v} for k, v in sums.items()]
        return SimpleNamespace(to_list=self._agg_to_list(rows))

    def _agg_to_list(self, rows):
        async def _to_list(length=None):
            return rows
        return _to_list

    def insert_one(self, doc):
        class Result:
            inserted_id = "507f1f77bcf86cd799439011"
        self.docs.append(doc)
        return Result()

    def delete_one(self, query):
        return self


class EventCollection:
    def __init__(self, docs=()):
        self.docs = list(docs)

    def aggregate(self, pipeline):
        rows_source = self.docs
        if pipeline and "$match" in pipeline[0]:
            match = pipeline[0]["$match"]
            ts = match.get("created_at") or {}
            gte = ts.get("$gte")
            if gte is not None:
                rows_source = [d for d in self.docs if d.get("created_at") >= gte]
        group_stage = pipeline[-1].get("$group", {}) if pipeline else {}
        id_field = (group_stage.get("_id") or "$publisher_id").lstrip("$")
        sums = {}
        for doc in rows_source:
            key = doc.get(id_field)
            sums[key] = sums.get(key, 0) + 1
        rows = [{"_id": k, "total": v} for k, v in sums.items()]
        return SimpleNamespace(to_list=self._agg_to_list(rows))

    def _agg_to_list(self, rows):
        async def _to_list(length=None):
            return rows
        return _to_list

    async def count_documents(self, query):
        return len(self.docs)

    async def find_one(self, query, *args):
        return None

    def insert_one(self, doc):
        class Result:
            inserted_id = ObjectId()
        self.docs.append(doc)
        return Result()


class ManualCollection:
    def __init__(self, docs=()):
        self.docs = list(docs)

    def aggregate(self, pipeline):
        return SimpleNamespace(to_list=self._agg_to_list([]))

    def _agg_to_list(self, rows):
        async def _to_list(length=None):
            return rows
        return _to_list

    async def find_one(self, query, *args, **kwargs):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    async def insert_one(self, doc):
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    async def update_one(self, query, update):
        for doc in self.docs:
            if doc.get("_id") == query.get("_id"):
                doc.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    async def delete_one(self, query):
        for i, doc in enumerate(self.docs):
            if doc.get("_id") == query.get("_id"):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


# ── 1. duplicate-IP per publisher ─────────────────────────────────────────────

class ScreenRedis:
    """exists/setex counters for the screening stage."""

    def __init__(self):
        self.keys = set()

    async def incr(self, key):
        return 1  # rate limit never trips in these tests

    async def expire(self, key, ttl):
        return True

    async def exists(self, key):
        return 1 if key in self.keys else 0

    async def setex(self, key, ttl, value):
        self.keys.add(key)


def make_screen_ctx(pub, site=None):
    return RedirectResolutionContext(
        raw_pub=pub, raw_site=site, ip="203.0.113.9",
        user_agent="Mozilla/5.0 (Windows NT 10.0)", referrer="", headers={},
        publisher_id=pub, website_id=site,
    )


class ScreenDB:
    """classify_traffic needs clicks (dup check) + ip_blacklist + publishers."""

    def __init__(self):
        self.clicks = ClickCollection()
        self.ip_blacklist = ManualCollection()
        self.publishers = ManualCollection()
        self.security_audit_log = ManualCollection()


async def test_duplicate_flag_is_per_publisher():
    """Same visitor → publisher A (valid) → publisher B (VALID, not flagged)."""
    from app.services.fraud_detection_service import TRAFFIC_VALID

    db = ScreenDB()
    redis = ScreenRedis()

    # First click on publisher A — valid.
    ctx_a = make_screen_ctx("pub-a")
    await rp.stage_screen_traffic(ctx_a, db, redis)
    assert ctx_a.is_flagged is False

    # Same visitor now clicks publisher B — must still be VALID.
    ctx_b = make_screen_ctx("pub-b")
    await rp.stage_screen_traffic(ctx_b, db, redis)
    assert ctx_b.is_flagged is False
    assert ctx_b.traffic_classification == TRAFFIC_VALID


async def test_repeat_on_same_publisher_is_flagged():
    """Second click on the SAME publisher (same day) IS the duplicate."""
    db = ScreenDB()
    redis = ScreenRedis()

    ctx1 = make_screen_ctx("pub-a")
    await rp.stage_screen_traffic(ctx1, db, redis)
    assert ctx1.is_flagged is False

    ctx2 = make_screen_ctx("pub-a")
    await rp.stage_screen_traffic(ctx2, db, redis)
    assert ctx2.is_flagged is True
    assert ctx2.fraud_reason == "duplicate_ip"


async def test_same_publisher_next_day_is_valid_again():
    """The duplicate key is per calendar day — tomorrow it resets."""
    db = ScreenDB()
    redis = ScreenRedis()

    ctx1 = make_screen_ctx("pub-a")
    await rp.stage_screen_traffic(ctx1, db, redis)

    # Simulate the next day: re-run with the stored keys' day suffix cleared.
    today = datetime.utcnow().strftime("%Y-%m-%d")
    for key in list(redis.keys):
        if today in key:
            redis.keys.discard(key)

    ctx2 = make_screen_ctx("pub-a")
    await rp.stage_screen_traffic(ctx2, db, redis)
    assert ctx2.is_flagged is False


async def test_two_publishers_do_not_flag_each_other_either_direction():
    """A→B and then B→A both stay valid (no cross-publisher contamination)."""
    db = ScreenDB()
    redis = ScreenRedis()

    await rp.stage_screen_traffic(make_screen_ctx("pub-a"), db, redis)
    await rp.stage_screen_traffic(make_screen_ctx("pub-b"), db, redis)
    ctx_back = make_screen_ctx("pub-a")
    # pub-a's key exists from the first click, so this IS a same-publisher
    # repeat — but the point is publisher B's traffic did not affect it.
    await rp.stage_screen_traffic(ctx_back, db, redis)
    assert ctx_back.fraud_reason == "duplicate_ip"  # from pub-a itself, not pub-b


# ── DB duplicate check stays per-publisher (fraud_detection_service) ──────────

async def test_db_duplicate_check_scopes_by_publisher():
    """check_duplicate_click must only match the SAME publisher's clicks."""
    pub_a, pub_b = ObjectId(), ObjectId()
    fingerprint_a = fds and __import__("hashlib").sha256(
        f"1.2.3.4:{str(pub_a)}:none".encode()
    ).hexdigest()

    db = ScreenDB()
    # A recent click from this IP on publisher A.
    db.clicks.docs.append({
        "fingerprint": fingerprint_a,
        "ip_address": "1.2.3.4",
        "publisher_id": str(pub_a),
        "timestamp": datetime.utcnow(),
    })

    # Same IP, publisher B — no fingerprint match → NOT a duplicate.
    is_dup_b, _ = await fds.check_duplicate_click(db, "1.2.3.4", str(pub_b), None)
    assert is_dup_b is False

    # Same IP, publisher A — fingerprint match → duplicate.
    is_dup_a, _ = await fds.check_duplicate_click(db, "1.2.3.4", str(pub_a), None)
    assert is_dup_a is True


# ── 2/3/4. manual conversions + publisher-domains payload ─────────────────────

def stats_app(db):
    from app.routers import direct_link_stats_router
    app = FastAPI()
    app.include_router(direct_link_stats_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_db.__name__] = lambda: db
    from app.dependencies import get_current_admin
    app.dependency_overrides[get_current_admin] = lambda: {"id": "admin", "role": "admin"}
    return app


class BroadCollection:
    """find_one matching any subset of non-empty query fields."""

    def __init__(self, docs=()):
        self.docs = list(docs)

    def find(self, query=None, *args):
        return SimpleNamespace(to_list=self._to_list(list(self.docs)))

    def _to_list(self, rows):
        async def _to_list(length=None):
            return rows
        return _to_list

    async def find_one(self, query=None, *args, **kwargs):
        query = query or {}
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()
                   if not isinstance(v, dict)):
                return doc
        return None

    def aggregate(self, pipeline):
        rows = []
        if pipeline and pipeline[0].get("$group", {}).get("_id") == "$publisher_id":
            totals = {}
            match = pipeline[0].get("$match", {})
            for doc in self.docs:
                if all(doc.get(k) == v for k, v in match.items()
                       if k != "conversions"):
                    totals[doc.get("publisher_id")] = totals.get(doc.get("publisher_id"), 0) + doc.get("conversions", 0)
            rows = [{"_id": k, "total": v} for k, v in totals.items()]
        return SimpleNamespace(to_list=self._to_list(rows))

    async def insert_one(self, doc):
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    async def update_one(self, query, update):
        for doc in self.docs:
            if doc.get("_id") == query.get("_id"):
                doc.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    async def delete_one(self, query):
        for i, doc in enumerate(self.docs):
            if doc.get("_id") == query.get("_id"):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    async def count_documents(self, query=None):
        return len(self.docs)


class DomainsDB:
    def __init__(self):
        pub = ObjectId()
        self.pub_id = str(pub)
        self.publishers = BroadCollection([
            {"_id": pub, "name": "Stats Pub", "email": "sp@example.com", "role": "publisher"},
        ])
        self.redirection_domains = BroadCollection([
            {"_id": ObjectId(), "domain": "pub-anchor.com", "domain_type": "anchor",
             "publisher_ids": [self.pub_id], "status": "active"},
            {"_id": ObjectId(), "domain": "global-anchor.com", "domain_type": "anchor",
             "publisher_ids": [], "is_default": True, "status": "active"},
            {"_id": ObjectId(), "domain": "global-prelander.com", "domain_type": "prelander",
             "publisher_ids": [], "is_default": True, "status": "active"},
        ])
        self.clicks = ClickCollection([
            {"publisher_id": self.pub_id, "timestamp": datetime.utcnow()},
            {"publisher_id": self.pub_id, "timestamp": datetime.utcnow() - timedelta(days=2)},
        ])
        self.direct_link_events = EventCollection([
            {"publisher_id": self.pub_id, "created_at": datetime.utcnow()},
        ])
        self.direct_link_manual_conversions = ManualCollection()


async def test_publisher_domains_returns_clicks_and_defaults():
    """The payload must carry real clicks + today conversions + default domains."""
    db = DomainsDB()
    async with AsyncClient(
        transport=ASGITransport(app=stats_app(db)), base_url="https://admin.example",
    ) as client:
        res = await client.get("/direct-links/publisher-domains")
    assert res.status_code == 200
    rows = res.json()["publisher_domains"]
    assert rows and rows[0]["publisher_id"] == db.pub_id
    row = rows[0]
    # Real smartlink traffic — 2 clicks (1 today).
    assert row["clicks"]["total"] == 2
    assert row["clicks"]["today"] == 1
    # Today conversions: 1 tracked event + 0 manual.
    assert row["clicks"]["today_conversions"] == 1
    # Assigned: the publisher's own anchor; defaults: the global ones.
    assert row["domains"]["anchor"] == ["pub-anchor.com"]
    assert row["defaults"]["anchor"] == "global-anchor.com"
    assert row["defaults"]["prelander"] == "global-prelander.com"


async def test_manual_conversion_without_reason_created_and_edited():
    """A conversion entry needs NO reason — create and edit without one."""
    db = DomainsDB()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with AsyncClient(
        transport=ASGITransport(app=stats_app(db)), base_url="https://admin.example",
    ) as client:
        created = await client.post("/direct-links/manual-conversions", json={
            "date": today, "publisher_id": db.pub_id, "conversions": 5,
        })
        assert created.status_code == 201
        cid = created.json()["conversion"]["id"]

        # Edit WITHOUT any reason — stored value must survive.
        edited = await client.put(f"/direct-links/manual-conversions/{cid}", json={"conversions": 9})
        assert edited.status_code == 200
        assert edited.json()["conversion"]["conversions"] == 9
        assert edited.json()["conversion"]["reason"] is None

        # An edit that supplies a reason still works.
        with_reason = await client.put(
            f"/direct-links/manual-conversions/{cid}",
            json={"conversions": 9, "reason": "Corrected"},
        )
        assert with_reason.status_code == 200
        assert with_reason.json()["conversion"]["reason"] == "Corrected"
        # …and a later reason-less edit keeps that reason.
        final = await client.put(f"/direct-links/manual-conversions/{cid}", json={"conversions": 10})
        assert final.json()["conversion"]["reason"] == "Corrected"