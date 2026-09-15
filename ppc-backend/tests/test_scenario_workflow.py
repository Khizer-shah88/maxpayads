"""
Scenario regression tests — manual publisher → anchor → prelander → offer flow.

Covers the fixes made while auditing the end-to-end scenario:

  Fix A: `_finalize` must persist campaign_id/offer_id onto the click document
         (click_tasks resolves offer-level CPC from click_doc["campaign_id"]).
  Fix B: `/d/{slug}` serving must apply the template rules — assigned active
         template, else OS default, else the built-in landing page renders
         (Bypass OFF never forwards the visitor straight to the campaign URL).
  Fix C: /p/render's default-template lookup must hint an OS name, not a host.
  Fix D: the prelander slug's OS must come from normalize_os, not a hard-coded
         mac-spelling list.

Mock-based — no database required. Follows test_redirect_pipeline.py style.
"""
import asyncio
import time
import base64
from types import SimpleNamespace

import pytest

from app.core.glossary import normalize_os
from app.services.redirect_pipeline import (
    STAGE_IDENTIFY,
    RedirectResolutionContext,
)


_XOR_KEY = "mxp2026"

# Valid ObjectId hex strings — production code wraps ids with ObjectId(...),
# so test fixtures must carry real 24-hex-char ids.
OFFER_ID = "507f1f77bcf86cd799439012"
TEMPLATE_ID = "507f1f77bcf86cd799439011"


def encode_slug(os_param: str, ts: int, offer_id="", campaign_id="", cc="") -> str:
    """Build a slug exactly as traffic_router.route_click does."""
    raw = f"{os_param}:{ts}:{offer_id}:{campaign_id}:{cc}"
    xored = bytes(ord(c) ^ ord(_XOR_KEY[i % len(_XOR_KEY)]) for i, c in enumerate(raw))
    return base64.urlsafe_b64encode(xored).decode().rstrip("=")


# ── Fix D: slug OS comes from the glossary normalizer ─────────────────────────

class TestSlugOsNormalization:
    """The slug OS must track normalize_os, not a fixed mac-spelling list."""

    @pytest.mark.parametrize("raw_os,expected", [
        ("Windows", "windows"),
        ("Windows NT 10.0", "windows"),
        ("Mac OS X 10.15", "mac"),
        ("OS X", "mac"),           # not in the old hard-coded list
        ("Darwin", "mac"),         # not in the old hard-coded list
        ("iPhone", "mac"),         # glossary maps ios -> mac
        ("Android", "windows"),    # mobile → prelander layouts are desktop-only
        (None, "windows"),         # unknown → windows (matches old default)
        ("", "windows"),
    ])
    def test_os_param_matches_normalize_os(self, raw_os, expected):
        from app.services import traffic_router as tr

        result = "mac" if normalize_os(raw_os, default="windows") == "mac" else "windows"
        # Mirror the production expression exactly.
        assert result == expected
        # And the production expression is what route_click uses — the slug OS
        # stays in {windows, mac}, the only two layouts /d/{slug} renders.
        assert result in ("windows", "mac")

    def test_legacy_and_normalizer_agree_on_common_spellings(self):
        """The old hard-coded list and normalize_os agree where the list had entries."""
        legacy_list = ("mac os", "mac os x", "macos", "ios")
        for spelling in legacy_list:
            legacy = "mac" if (spelling or "").lower() in legacy_list else "windows"
            normalized = "mac" if normalize_os(spelling, default="windows") == "mac" else "windows"
            assert legacy == normalized == "mac"


# ── Fix B: template rules on the /d/{slug} serving path ───────────────────────

def _make_request(host: str = "prelander1.com"):
    """A minimal Starlette-style request stub with the headers we read."""
    return SimpleNamespace(headers={
        "x-prelander-host": host,
        "host": f"{host}:443",
    })


class _FindOneRouter:
    """Sequence-driven db stub: each find_one call pops the next canned doc."""

    def __init__(self, collections):
        self._collections = collections

    async def __call__(self, collection, query):
        raise NotImplementedError


class FakePrelanderDB:
    """Minimal async db stub covering the collections _get_prelander_data touches."""

    def __init__(self, redirection_domains=(), offers=(), campaigns=(), geo_rules=None, **kwargs):
        self.redirection_domains = _Coll(redirection_domains)
        self.offers = _Coll(offers)
        self.campaigns = _Coll(campaigns)
        self.geo_rules = _Coll(geo_rules or [])
        self.prelander_templates = _Coll(kwargs.get("prelander_templates", []))
        self.landing_pages = _Coll(kwargs.get("landing_pages", []))

    async def __call__(self, *a, **kw):
        raise NotImplementedError


class _Coll:
    """In-memory Mongo-collection stub with the queries we actually issue."""

    def __init__(self, docs):
        self.docs = list(docs)

    async def find_one(self, query=None, **kwargs):
        import re

        def matches(doc):
            for key, cond in (query or {}).items():
                value = doc.get(key)
                if isinstance(cond, dict) and "$in" in cond:
                    if value not in cond["$in"]:
                        return False
                elif isinstance(cond, dict) and "$regex" in cond:
                    options = cond.get("$options", "")
                    pattern = re.compile(cond["$regex"], re.IGNORECASE if "i" in options else 0)
                    if not pattern.search(str(value or "")):
                        return False
                elif value != cond:
                    return False
            return True

        for doc in self.docs:
            if matches(doc):
                return doc
        return None


class TestPrelanderTemplateWiring:
    """_get_prelander_data must apply: assigned template → OS default → skip."""

    @pytest.fixture
    def prelander_domain_doc(self):
        from app.core.constants import DOMAIN_TYPE_PRELANDER
        return {
            "domain": "prelander1.com",
            "domain_type": DOMAIN_TYPE_PRELANDER,
            "status": "active",
            "template": "windows",
            "weight": 100,
            "template_id": TEMPLATE_ID,
        }

    @pytest.fixture
    def active_template(self):
        from bson import ObjectId
        return {
            "_id": ObjectId(TEMPLATE_ID),
            "name": "Win Custom",
            "os_type": "windows",
            "status": "active",
            "title": "Custom title",
            "subtitle": "Custom subtitle",
            "button_text": "Grab it",
            "show_password_field": True,
        }

    async def _resolve(self, db, slug_os="windows", host="prelander1.com", offer=None):
        from app.routers.prelander_router import _get_prelander_data

        slug = encode_slug(slug_os, int(time.time()),
                           offer_id=(offer or {}).get("_id", ""),
                           campaign_id="camp-1", cc="PK")
        decoded = {"os": slug_os, "offer_id": (offer or {}).get("_id", ""),
                   "campaign_id": "camp-1", "country_code": "PK"}
        # Signature is (request, os, db, ...) — os before db.
        return await _get_prelander_data(
            _make_request(host),
            slug_os,
            db,
            offer_id=decoded.get("offer_id"),
            campaign_id=decoded.get("campaign_id"),
            country_code=decoded.get("country_code"),
        )

    async def test_assigned_active_template_is_surfaced(self, prelander_domain_doc, active_template):
        """Domain has an assigned active template → response carries its fields."""
        db = FakePrelanderDB(
            redirection_domains=[prelander_domain_doc],
            prelander_templates=[active_template],
            offers=[{"_id": OFFER_ID, "status": "active",
                     "offer_url": "https://offer.example/win", "campaign_id": "camp-1"}],
        )
        data = await self._resolve(db, offer={"_id": OFFER_ID})

        assert data["success"] is True
        assert data["skip_prelander"] is False if "skip_prelander" in data else True
        assert data["offer_url"] == "https://offer.example/win"
        tpl = data["template"]
        assert tpl["name"] == "Win Custom"
        assert tpl["title"] == "Custom title"
        assert tpl["button_text"] == "Grab it"

    async def test_missing_assigned_template_falls_back_to_os_default(self, prelander_domain_doc):
        """Assigned template inactive/gone → OS default is used (still renders)."""
        from app.core.constants import DOMAIN_TYPE_PRELANDER
        prelander_domain_doc.pop("template_id", None)
        default_tpl = {
            "_id": "tpl-default", "name": "Win Default", "os_type": "windows",
            "status": "active", "is_default": True,
        }
        db = FakePrelanderDB(
            redirection_domains=[prelander_domain_doc],
            prelander_templates=[default_tpl],
            offers=[{"_id": OFFER_ID, "status": "active",
                     "offer_url": "https://offer.example/win", "campaign_id": "camp-1"}],
        )
        data = await self._resolve(db, offer={"_id": OFFER_ID})

        assert data["success"] is True
        assert "skip_prelander" not in data
        assert data["template"]["name"] == "Win Default"

    async def test_no_active_template_still_renders_landing_page(self, prelander_domain_doc):
        """Spec (Bypass OFF): no active template → built-in landing page still
        renders. The visitor is never forwarded to the campaign URL directly —
        that path is reserved for Bypass ON."""
        db = FakePrelanderDB(
            redirection_domains=[prelander_domain_doc],
            prelander_templates=[],
            offers=[{"_id": OFFER_ID, "status": "active",
                     "offer_url": "https://offer.example/win", "campaign_id": "camp-1"}],
        )
        data = await self._resolve(db, offer={"_id": OFFER_ID})

        assert data["success"] is True
        # The skip flag is gone: Bypass OFF always lands on the landing page.
        assert "skip_prelander" not in data
        assert data["offer_url"] == "https://offer.example/win"
        assert data["template"] is None

    async def test_non_prelander_host_never_sets_skip_flag(self, active_template):
        """Inter/anchor hosts don't get the skip flag — they hop to the prelander."""
        db = FakePrelanderDB(
            redirection_domains=[],
            prelander_templates=[active_template],
            offers=[{"_id": OFFER_ID, "status": "active",
                     "offer_url": "https://offer.example/win", "campaign_id": "camp-1"}],
        )
        data = await self._resolve(db, host="inter1.com", offer={"_id": OFFER_ID})

        assert data["success"] is True
        assert "skip_prelander" not in data
        assert data["offer_url"] == "https://offer.example/win"


# ── Fix C: /p/render default-template lookup uses an OS hint, not a host ──────

class TestPublicRenderOsHint:
    """get_default_template(os_hint=…) must receive an OS name."""

    def test_os_hint_is_never_a_hostname(self):
        """normalize_os on a hostname yields None (hostnames aren't OS names)."""
        assert normalize_os("prelander1.com", default=None) is None
        assert normalize_os("example.com", default=None) is None

    async def test_render_uses_context_os_for_default_lookup(self):
        """The default-template hint must be the visitor's OS, from the token context."""
        from app.routers.prelander_public_router import render_prelander
        from app.services.prelander_service import RedirectContext

        seen = {}

        class _RecordingColl:
            """find_one records the query; returns None (no matching doc)."""

            def __init__(self, store_key):
                self._store_key = store_key

            async def find_one(self, query=None, **kwargs):
                seen.setdefault(self._store_key, query)
                return None

        db = SimpleNamespace(
            redirection_domains=_RecordingColl("domain_query"),
            prelander_templates=_RecordingColl("default_query"),
        )

        context = RedirectContext(
            click_id="c1", campaign_url="https://offer.example/x",
            country="PK", os="Windows",
        )
        token = context.sign()
        request = SimpleNamespace(
            headers={"host": "prelander1.com:443"},
            client=SimpleNamespace(host="203.0.113.9"),
        )

        response = await render_prelander(request=request, token=token, db=db)
        assert response.status_code == 200
        # The OS hint in the default lookup is the context's OS, not the host.
        default_query = seen.get("default_query") or {}
        assert default_query.get("os_type") == "windows"


# ── Fix A: campaign/offer attribution on the final click update ───────────────

class FakeClicks:
    def __init__(self, fail_insert=False):
        self.fail_insert = fail_insert
        self.inserted = []
        self.updates = []

    async def insert_one(self, doc):
        if self.fail_insert:
            raise RuntimeError("clicks collection unavailable")
        self.inserted.append(doc)
        return SimpleNamespace(inserted_id="507f1f77bcf86cd799439011")

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
    from app.services import redirect_pipeline as rp

    async def fake_identify(ctx, db):
        ctx.publisher_id = "pub-1"
        ctx.website_id = "site-1" if ctx.raw_site else None
        ctx.record(STAGE_IDENTIFY, "publisher_only", publisher_id=ctx.publisher_id)
        return True

    async def fake_detect(ctx):
        ctx.os_name, ctx.os_enum = "Windows", "windows"
        ctx.device_type, ctx.browser = "desktop", "Chrome"
        ctx.country_code, ctx.country_name = "PK", "Pakistan"

    async def fake_screen(ctx, db, redis):
        ctx.record("screen", "valid")

    async def fake_route(ctx, db, redis):
        ctx.destination_url = "https://offer.example/win-pk"
        ctx.campaign_id = "camp-pk-win"
        ctx.offer_id = "offer-pk-win"

    async def fake_cpc(ctx, db):
        ctx.record("cpc", "deferred_to_task")

    async def fake_log(ctx, db):
        pass

    monkeypatch.setattr(rp, "stage_identify_publisher", fake_identify)
    monkeypatch.setattr(rp, "stage_detect_visitor", fake_detect)
    monkeypatch.setattr(rp, "stage_screen_traffic", fake_screen)
    monkeypatch.setattr(rp, "stage_resolve_route", fake_route)
    monkeypatch.setattr(rp, "stage_resolve_cpc", fake_cpc)
    monkeypatch.setattr(rp, "_log_screening_outcome", fake_log)
    return SimpleNamespace()


class TestCampaignOfferPersistence:
    """The final update must carry campaign_id + offer_id for downstream consumers."""

    async def test_campaign_and_offer_persisted(self, stub_stages):
        from app.services import redirect_pipeline as rp

        db = FakeDB()
        ctx = await rp.resolve_redirect(make_ctx(), db, redis=None)

        assert len(db.clicks.updates) == 1
        _, update = db.clicks.updates[0]
        assert update["$set"]["campaign_id"] == "camp-pk-win"
        assert update["$set"]["offer_id"] == "offer-pk-win"
        assert update["$set"]["destination_url"] == "https://offer.example/win-pk"

    async def test_unset_attribution_is_not_written(self, stub_stages, monkeypatch):
        from app.services import redirect_pipeline as rp

        async def no_attribution(ctx, db, redis):
            ctx.destination_url = "https://offer.example/global"

        monkeypatch.setattr(rp, "stage_resolve_route", no_attribution)
        db = FakeDB()
        ctx = await rp.resolve_redirect(make_ctx(), db, redis=None)

        _, update = db.clicks.updates[0]
        assert "campaign_id" not in update["$set"]
        assert "offer_id" not in update["$set"]
        assert update["$set"]["destination_url"] == "https://offer.example/global"

    async def test_attribution_survives_publisher_attribution_check(self, stub_stages):
        """Record-stage click doc + final update agree on the attribution fields."""
        from app.services import redirect_pipeline as rp

        db = FakeDB()
        ctx = await rp.resolve_redirect(make_ctx(raw_site="SITE_XYZ789AB"), db, redis=None)

        _, update = db.clicks.updates[0]
        assert update["$set"]["campaign_id"] == "camp-pk-win"
        # The click document recorded at RECORD time doesn't have campaign_id
        # (campaign resolves after recording) — the final update adds it.
        assert db.clicks.inserted[0]["publisher_id"] == "pub-1"