"""Statistics OS filters must match every stored OS spelling.

Click documents store `os` exactly as the user-agent parser reports it —
"Mac OS X" for Macs — while the Statistics pages filter with display names
("macOS"). A bare substring regex cannot bridge that ("macos" is not a
substring of "Mac OS X"), so every OS filter now goes through
`app.core.glossary.os_filter`.

Covers the helper itself plus one endpoint per router that filters clicks by
OS: admin /clicks, /analytics/click-stats, /publisher/reports.
"""
import re
from datetime import datetime
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.constants import OS_ANDROID, OS_IOS, OS_MAC, OS_WINDOWS
from app.core.glossary import os_filter
from app.dependencies import get_current_admin, get_current_active_publisher, get_db
from app.routers import analytics_router, click_router, publisher_router


# ── the helper ────────────────────────────────────────────────────────────────

def _matches(term, stored):
    cond = os_filter(term)
    assert cond is not None, f"os_filter({term!r}) returned None"
    return re.search(cond["$regex"], stored, re.IGNORECASE) is not None


def test_macos_filter_matches_every_stored_mac_spelling():
    for term in ("macOS", "macos", "Mac OS X", "Mac", "Mac OS X 10.15"):
        for stored in ("Mac OS X", "macOS", "Mac", "Darwin", "mac os x 10.15"):
            assert _matches(term, stored), f"{term!r} must match {stored!r}"


def test_macos_filter_does_not_swallow_other_buckets():
    for stored in ("iOS", "iPhone", "Windows", "Android", "Linux"):
        assert not _matches("macOS", stored), f"macOS must not match {stored!r}"


def test_ios_is_its_own_statistics_bucket():
    """Statistics lists macOS and iOS separately; routing buckets iOS into
    mac, but the stats filter must keep them apart (and Darwin is a CLI OS,
    not a phone)."""
    assert _matches("iOS", "iOS")
    assert _matches("iOS", "iPhone OS")
    assert not _matches("iOS", "Mac OS X")
    assert not _matches("iOS", "Darwin")


@pytest.mark.parametrize("term,stored", [
    ("Windows", "Windows"),
    ("windows", "Windows"),
    ("Windows", "Windows NT 10.0"),
    ("Android", "Android"),
    ("Android", "Android 14"),
    ("Linux", "Linux"),
    ("Chrome OS", "Chrome OS"),
    ("Chrome OS", "Chromium OS"),
])
def test_common_terms_match_their_stored_spelling(term, stored):
    assert _matches(term, stored)


def test_unknown_term_degrades_to_the_old_substring_match():
    """An unrecognised OS term must keep the previous escaped-substring filter
    rather than filtering everything out."""
    cond = os_filter("Plan 9")
    assert cond == {"$regex": re.escape("Plan 9"), "$options": "i"}


def test_empty_term_builds_no_filter():
    assert os_filter("") is None
    assert os_filter("   ") is None
    assert os_filter(None) is None


def test_filter_never_breaks_on_regex_metacharacters():
    cond = os_filter("os.x")
    # Unknown term → escaped, so the dot is literal.
    assert not re.search(cond["$regex"], "osax", re.IGNORECASE)
    assert re.search(cond["$regex"], "os.x", re.IGNORECASE)


# ── endpoint fakes ────────────────────────────────────────────────────────────

def _regex_hit(value, cond):
    flags = re.IGNORECASE if "i" in cond.get("$options", "") else 0
    return value is not None and re.search(cond["$regex"], str(value), flags) is not None


def matches(doc, query):
    for key, cond in query.items():
        actual = doc.get(key)
        if isinstance(cond, dict) and "$regex" in cond:
            if not _regex_hit(actual, cond):
                return False
        elif actual != cond:
            return False
    return True


def _path(doc, dotted):
    for part in dotted.split("."):
        doc = doc.get(part) if isinstance(doc, dict) else None
    return doc


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=None):
        fields = [(key, direction)] if isinstance(key, str) else key
        for name, order in reversed(fields):
            self.docs.sort(key=lambda d: _path(d, name) or datetime.min, reverse=order == -1)
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    def limit(self, n):
        self.docs = self.docs[:n] if n else self.docs
        return self

    async def to_list(self, length=None):
        return self.docs[:length] if length else self.docs

    async def __aiter__(self):
        for doc in self.docs:
            yield doc


def _eval(expr, doc):
    """Evaluate the tiny expression subset the stats pipelines use."""
    if isinstance(expr, str) and expr.startswith("$"):
        value = doc.get(expr[1:])
        return 0 if value is None else value
    if isinstance(expr, dict):
        if "$year" in expr:
            return _eval(expr["$year"], doc).year
        if "$month" in expr:
            return _eval(expr["$month"], doc).month
        if "$dayOfMonth" in expr:
            return _eval(expr["$dayOfMonth"], doc).day
        if "$cond" in expr:
            cond_expr, then, other = expr["$cond"]
            left, right = cond_expr["$eq"]
            return _eval(then, doc) if _eval(left, doc) == _eval(right, doc) else _eval(other, doc)
        return {k: _eval(v, doc) for k, v in expr.items()}
    return expr


class FakeCollection:
    def __init__(self, docs=()):
        self.docs = list(docs)

    def find(self, query=None, *args):
        return FakeCursor([dict(d) for d in self.docs if matches(d, query or {})])

    async def count_documents(self, query):
        return len([d for d in self.docs if matches(d, query)])

    def aggregate(self, pipeline):
        docs = [dict(d) for d in self.docs]
        for stage in pipeline:
            if "$match" in stage:
                docs = [d for d in docs if matches(d, stage["$match"])]
            elif "$group" in stage:
                grouped = {}
                for d in docs:
                    gid = _eval(stage["$group"]["_id"], d)
                    bucket = grouped.setdefault(repr(gid), {"_id": gid})
                    for field, acc in stage["$group"].items():
                        if field == "_id":
                            continue
                        (expr,) = acc.values()
                        prev = bucket.get(field, 0)
                        value = _eval(expr, d)
                        bucket[field] = prev + (value if isinstance(value, (int, float)) else 1)
                docs = list(grouped.values())
            elif "$sort" in stage:
                for name, order in reversed(list(stage["$sort"].items())):
                    docs.sort(key=lambda d: _path(d, name) or 0, reverse=order == -1)
            elif "$limit" in stage:
                docs = docs[:stage["$limit"]]
        return FakeCursor(docs)


def seed_clicks(db):
    """Clicks storing `os` exactly as the UA parser reports it."""
    db.clicks = FakeCollection([
        {"_id": ObjectId(), "os": "Mac OS X", "status": "valid", "earnings": 0.5,
         "device_type": "desktop", "browser": "Safari", "country_code": "US",
         "timestamp": datetime(2026, 9, 28, 10, 0, 0)},
        {"_id": ObjectId(), "os": "macOS", "status": "valid", "earnings": 0.2,
         "device_type": "desktop", "browser": "Chrome", "country_code": "US",
         "timestamp": datetime(2026, 9, 28, 11, 0, 0)},
        {"_id": ObjectId(), "os": "iOS", "status": "valid", "earnings": 0.1,
         "device_type": "mobile", "browser": "Safari", "country_code": "US",
         "timestamp": datetime(2026, 9, 28, 12, 0, 0)},
        {"_id": ObjectId(), "os": "Windows", "status": "valid", "earnings": 0.3,
         "device_type": "desktop", "browser": "Chrome", "country_code": "DE",
         "timestamp": datetime(2026, 9, 28, 13, 0, 0)},
    ])


def stats_app(db):
    app = FastAPI()
    app.include_router(click_router.router)
    app.include_router(analytics_router.router)
    app.include_router(publisher_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_admin] = lambda: {"id": "admin-1", "role": "admin"}
    app.dependency_overrides[get_current_active_publisher] = lambda: {"id": "pub-1", "role": "publisher"}
    return app


# ── the endpoints ─────────────────────────────────────────────────────────────

async def test_admin_clicks_macos_filter_includes_mac_os_x():
    from copy import deepcopy

    db = SimpleNamespace(clicks=FakeCollection(), websites=FakeCollection())
    seed_clicks(db)
    saved = deepcopy(db.clicks.docs)
    app = stats_app(db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/clicks", params={"os": "macOS"})
        assert res.status_code == 200
        os_values = [c["os"] for c in res.json()["clicks"]]
        assert set(os_values) == {"Mac OS X", "macOS"}
        assert "iOS" not in os_values and "Windows" not in os_values
        assert res.json()["total"] == 2

    # The endpoint must not have mutated the stored docs.
    assert [d["os"] for d in saved] == ["Mac OS X", "macOS", "iOS", "Windows"]


async def test_analytics_click_stats_macos_filter_includes_mac_os_x():
    db = SimpleNamespace(clicks=FakeCollection(), websites=FakeCollection())
    seed_clicks(db)
    app = stats_app(db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/analytics/click-stats", params={"os": "macOS"})
        assert res.status_code == 200
        body = res.json()
        assert body["totals"]["total"] == 2  # Mac OS X + macOS, NOT the iOS click
        assert body["totals"]["valid"] == 2
        os_rows = {row["name"]: row["value"] for row in body["distribution"]["os"]}
        assert os_rows == {"Mac OS X": 1, "macOS": 1}


async def test_publisher_reports_macos_filter_includes_mac_os_x():
    db = SimpleNamespace(clicks=FakeCollection(), websites=FakeCollection())
    seed_clicks(db)
    for doc in db.clicks.docs:
        doc["publisher_id"] = "pub-1"
    app = stats_app(db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/publisher/reports", params={"os": "macOS"})
        assert res.status_code == 200
        body = res.json()
        os_values = [c["os"] for c in body["clicks"]]
        assert set(os_values) == {"Mac OS X", "macOS"}
        assert body["summary"]["total"] == 2


async def test_ios_filter_stays_separate_from_macos():
    db = SimpleNamespace(clicks=FakeCollection(), websites=FakeCollection())
    seed_clicks(db)
    app = stats_app(db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/clicks", params={"os": "iOS"})
        assert res.status_code == 200
        os_values = [c["os"] for c in res.json()["clicks"]]
        assert os_values == ["iOS"]