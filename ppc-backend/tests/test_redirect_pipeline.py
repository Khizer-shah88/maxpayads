"""
Redirect pipeline — backbone tests.

These cover the two guarantees the pipeline exists to make:

  1. The visitor always leaves with a URL. Every failure mode — unknown
     publisher, click write failure, routing exception — still resolves.
  2. Publisher attribution is fixed once and never re-derived, so it survives
     every stage.

Plus the trace itself: stages recorded in execution order, in a shape that is
safe to store on the click document.

`app.services.redirect_pipeline` imports nothing from the app at module level,
so these run without a database.
"""
import pytest

from app.services import redirect_pipeline as rp
from app.services.redirect_pipeline import (
    FALLBACK_URL,
    STAGE_CPC,
    STAGE_DELIVER,
    STAGE_IDENTIFY,
    STAGE_RECORD,
    STAGE_SCREEN,
    RedirectResolutionContext,
)


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeClicks:
    def __init__(self, fail_insert=False):
        self.fail_insert = fail_insert
        self.inserted = []
        self.updates = []

    async def insert_one(self, doc):
        if self.fail_insert:
            raise RuntimeError("clicks collection unavailable")
        self.inserted.append(doc)

        class Result:
            inserted_id = "507f1f77bcf86cd799439011"

        return Result()

    async def update_one(self, query, update):
        self.updates.append((query, update))


class FakeDB:
    def __init__(self, fail_insert=False):
        self.clicks = FakeClicks(fail_insert=fail_insert)


def make_ctx(**overrides):
    defaults = dict(
        raw_pub="PUB_ABC12XYZ",
        raw_site=None,
        ip="203.0.113.9",
        user_agent="Mozilla/5.0 (Windows NT 10.0)",
        referrer="",
        headers={},
    )
    defaults.update(overrides)
    return RedirectResolutionContext(**defaults)


@pytest.fixture
def stub_stages(monkeypatch):
    """
    Replace the stages that need real services with controllable stubs, leaving
    the orchestrator itself under test.
    """
    calls = {"route": 0, "cpc": 0, "screen_log": 0}

    async def fake_identify(ctx, db):
        ctx.publisher_id = "pub-1"
        ctx.website_id = "site-1" if ctx.raw_site else None
        ctx.record(STAGE_IDENTIFY, "publisher_only", publisher_id=ctx.publisher_id)
        return True

    async def fake_detect(ctx):
        ctx.os_name, ctx.os_enum = "Windows", "windows"
        ctx.device_type, ctx.browser = "desktop", "Chrome"
        ctx.country_code, ctx.country_name = "US", "United States"
        ctx.record("detect_visitor", "detected")

    async def fake_screen(ctx, db, redis):
        ctx.record(STAGE_SCREEN, "valid")

    async def fake_route(ctx, db, redis):
        calls["route"] += 1
        ctx.destination_url = "https://offer.example/landing"
        ctx.campaign_id = "camp-1"

    async def fake_cpc(ctx, db):
        calls["cpc"] += 1
        ctx.record(STAGE_CPC, "deferred_to_task")

    async def fake_log(ctx, db):
        calls["screen_log"] += 1

    monkeypatch.setattr(rp, "stage_identify_publisher", fake_identify)
    monkeypatch.setattr(rp, "stage_detect_visitor", fake_detect)
    monkeypatch.setattr(rp, "stage_screen_traffic", fake_screen)
    monkeypatch.setattr(rp, "stage_resolve_route", fake_route)
    monkeypatch.setattr(rp, "stage_resolve_cpc", fake_cpc)
    monkeypatch.setattr(rp, "_log_screening_outcome", fake_log)
    return calls


# ── the context and its trace ─────────────────────────────────────────────────

def test_trace_records_stages_in_execution_order():
    ctx = make_ctx()
    ctx.record("a", "one")
    ctx.record("b", "two", detail_key="v")
    assert [d.stage for d in ctx.trace] == ["a", "b"]
    assert ctx.trace[1].detail == {"detail_key": "v"}
    assert all(d.elapsed_ms >= 0 for d in ctx.trace)


def test_trace_detail_is_reduced_to_storable_values():
    ctx = make_ctx()
    ctx.record("s", "o", long="x" * 1000, nested={"a": [1, 2, 3]}, obj=object())
    detail = ctx.trace_as_list()[0]["detail"]
    assert len(detail["long"]) == rp.MAX_DETAIL_CHARS
    assert detail["nested"] == {"a": [1, 2, 3]}
    assert isinstance(detail["obj"], str)


def test_trace_is_bounded():
    ctx = make_ctx()
    for i in range(rp.MAX_TRACE_ENTRIES + 25):
        ctx.record("s", f"o{i}")
    assert len(ctx.trace) == rp.MAX_TRACE_ENTRIES


def test_summary_names_the_whole_journey():
    ctx = make_ctx()
    ctx.publisher_id, ctx.campaign_id = "pub-1", "camp-1"
    ctx.destination_url = "https://offer.example/x"
    ctx.record("resolve_campaign", "matched")
    summary = ctx.summary()
    assert "pub=pub-1" in summary
    assert "campaign=camp-1" in summary
    assert "resolve_campaign:matched" in summary


def test_click_fields_carry_attribution_and_truncate():
    ctx = make_ctx(user_agent="U" * 900, referrer="R" * 900)
    ctx.publisher_id, ctx.website_id = "pub-1", "site-1"
    fields = ctx.to_click_fields()
    assert fields["publisher_id"] == "pub-1"
    assert fields["website_id"] == "site-1"
    assert len(fields["user_agent"]) == 500
    assert len(fields["referrer"]) == 500


def test_empty_referrer_is_stored_as_none():
    assert make_ctx(referrer="").to_click_fields()["referrer"] is None


# ── the pipeline ──────────────────────────────────────────────────────────────

async def test_valid_click_routes_and_defers_cpc(stub_stages):
    db = FakeDB()
    ctx = await rp.resolve_redirect(make_ctx(), db, redis=None)

    assert ctx.destination_url == "https://offer.example/landing"
    assert stub_stages["route"] == 1
    assert stub_stages["cpc"] == 1
    assert len(db.clicks.inserted) == 1
    assert db.clicks.inserted[0]["publisher_id"] == "pub-1"
    assert ctx.trace[-1].stage == STAGE_DELIVER
    assert ctx.trace[-1].outcome == "routed"


async def test_unknown_publisher_falls_back_without_routing(monkeypatch, stub_stages):
    async def no_publisher(ctx, db):
        ctx.record(STAGE_IDENTIFY, "unknown_publisher")
        return False

    monkeypatch.setattr(rp, "stage_identify_publisher", no_publisher)
    db = FakeDB()
    ctx = await rp.resolve_redirect(make_ctx(), db, redis=None)

    assert ctx.destination_url == FALLBACK_URL
    assert stub_stages["route"] == 0
    assert db.clicks.inserted == []          # nothing to attribute the click to
    assert ctx.trace[-1].outcome == "fallback_unknown_publisher"


async def test_blocked_traffic_never_reaches_an_offer(monkeypatch, stub_stages):
    async def blocked(ctx, db, redis):
        ctx.is_blocked = True
        ctx.click_status = "invalid"
        ctx.fraud_reason = "bot_user_agent"
        ctx.record(STAGE_SCREEN, "blocked")

    monkeypatch.setattr(rp, "stage_screen_traffic", blocked)
    db = FakeDB()
    ctx = await rp.resolve_redirect(make_ctx(), db, redis=None)

    assert ctx.destination_url == FALLBACK_URL
    assert stub_stages["route"] == 0
    assert stub_stages["screen_log"] == 1
    # The click is still recorded — a blocked click is still a click.
    assert db.clicks.inserted[0]["status"] == "invalid"
    assert ctx.trace[-1].outcome == "fallback_blocked"


async def test_flagged_traffic_is_logged_but_still_routed(monkeypatch, stub_stages):
    async def flagged(ctx, db, redis):
        ctx.is_flagged = True
        ctx.click_status = "invalid"
        ctx.record(STAGE_SCREEN, "flagged")

    monkeypatch.setattr(rp, "stage_screen_traffic", flagged)
    db = FakeDB()
    ctx = await rp.resolve_redirect(make_ctx(), db, redis=None)

    assert ctx.destination_url == "https://offer.example/landing"
    assert stub_stages["route"] == 1
    assert stub_stages["screen_log"] == 1
    assert ctx.trace[-1].outcome == "routed"


async def test_click_write_failure_still_delivers_the_visitor(stub_stages):
    db = FakeDB(fail_insert=True)
    ctx = await rp.resolve_redirect(make_ctx(), db, redis=None)

    assert ctx.destination_url == FALLBACK_URL
    assert stub_stages["route"] == 0
    assert any(d.outcome == "write_failed" for d in ctx.trace)
    assert ctx.trace[-1].outcome == "fallback_click_not_recorded"


async def test_routing_exception_still_delivers_the_visitor(monkeypatch):
    """stage_resolve_route swallows routing errors — the visitor is never dropped."""
    async def exploding_route_click(click_data, db, redis, ctx=None):
        raise RuntimeError("targeting engine down")

    import app.services.traffic_router as tr
    monkeypatch.setattr(tr, "route_click", exploding_route_click)

    ctx = make_ctx()
    ctx.click_document = {"publisher_id": "pub-1"}
    await rp.stage_resolve_route(ctx, db=FakeDB(), redis=None)

    assert ctx.destination_url == FALLBACK_URL
    assert any(d.outcome == "routing_error" for d in ctx.trace)


async def test_flagged_click_is_not_queued_for_cpc():
    ctx = make_ctx()
    ctx.is_flagged = True
    await rp.stage_resolve_cpc(ctx, db=FakeDB())
    entry = ctx.trace[-1]
    assert entry.stage == STAGE_CPC
    assert entry.outcome == "skipped_flagged"


async def test_publisher_attribution_survives_every_stage(stub_stages):
    """Nothing after identify_publisher may re-derive or lose the publisher."""
    db = FakeDB()
    ctx = await rp.resolve_redirect(make_ctx(raw_site="SITE_XYZ789AB"), db, redis=None)

    assert ctx.publisher_id == "pub-1"
    assert ctx.website_id == "site-1"
    assert db.clicks.inserted[0]["publisher_id"] == "pub-1"
    assert db.clicks.inserted[0]["website_id"] == "site-1"
    recorded = next(d for d in ctx.trace if d.stage == STAGE_RECORD)
    assert recorded.detail["publisher_id"] == "pub-1"


async def test_destination_and_trace_are_persisted(stub_stages):
    db = FakeDB()
    ctx = await rp.resolve_redirect(make_ctx(), db, redis=None)

    assert len(db.clicks.updates) == 1
    _, update = db.clicks.updates[0]
    assert update["$set"]["destination_url"] == ctx.destination_url
    stages = [e["stage"] for e in update["$set"]["resolution_trace"]]
    assert stages[0] == STAGE_IDENTIFY
    assert stages[-1] == STAGE_DELIVER
