"""
Landing Pages — Prelander binding rules.

Covers the two admin requirements:
1. Add Landing Page offers ONLY the remaining (not yet bound) prelander
   domains — already-bound domains never reappear in the create form.
2. A prelander domain's active/paused status is the pool include/exclude
   switch: active = in the weighted pool, paused = fully configured but
   receives no traffic (select_active_prelander already enforces this —
   see test_publisher_domain_rules.py).

Uses an in-memory db stub (no MongoDB connection needed).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


class _FindOneDb:
    """Minimal async db stub: canned find_one docs per collection."""

    def __init__(self, redirection_domains=(), landing_pages=(), prelander_templates=()):
        self.redirection_domains = MagicMock()
        self.landing_pages = MagicMock()
        self.prelander_templates = MagicMock()
        self.redirection_domains.find_one = AsyncMock(
            side_effect=lambda q, **kw: _match(next((d for d in redirection_domains if _matches(d, q)), None), q)
        )
        self.landing_pages.find_one = AsyncMock(
            side_effect=lambda q, **kw: _match(next((d for d in landing_pages if _matches(d, q)), None), q)
        )
        self.prelander_templates.find_one = AsyncMock(
            side_effect=lambda q, **kw: _match(next((d for d in prelander_templates if _matches(d, q)), None), q)
        )


class _Doc(dict):
    """Mongo doc whose $ne queries are answerable."""

    def __ne__(self, other):  # not used by matching — placeholder
        return True


def _matches(doc, query):
    if doc is None:
        return False
    for key, cond in (query or {}).items():
        value = doc.get(key)
        if isinstance(cond, dict):
            if "$ne" in cond and value == cond["$ne"]:
                return False
            if "$in" in cond and value not in cond["$in"]:
                return False
        elif value != cond:
            return False
    return True


def _match(doc, query):
    return dict(doc) if doc is not None else None


@pytest.mark.asyncio
class TestValidatePrelanderBindings:
    async def test_bound_domain_rejected_as_duplicate(self):
        from app.routers.landing_page_router import _validate_prelander_bindings

        db = _FindOneDb(
            redirection_domains=[
                {"domain": "pre.example.com", "domain_type": "prelander", "status": "active"},
            ],
            landing_pages=[
                {"prelander_domain": "pre.example.com", "name": "Existing LP"},
            ],
        )
        with pytest.raises(ValueError, match="already bound"):
            await _validate_prelander_bindings(db, {"prelander_domain": "pre.example.com"})

    async def test_own_binding_survives_update_duplicate_check(self):
        from app.routers.landing_page_router import _validate_prelander_bindings
        from bson import ObjectId

        page_id = str(ObjectId())
        db = _FindOneDb(
            redirection_domains=[
                {"domain": "pre.example.com", "domain_type": "prelander", "status": "paused"},
            ],
            # The page being updated is its own binding — the $ne excludes it.
            landing_pages=[{"_id": ObjectId(page_id), "prelander_domain": "pre.example.com"}],
        )
        # Paused domains are BINDABLE (status is the pool switch, not the binding).
        await _validate_prelander_bindings(
            db, {"prelander_domain": "pre.example.com"}, exclude_page_id=page_id
        )

    async def test_unknown_domain_rejected(self):
        from app.routers.landing_page_router import _validate_prelander_bindings

        db = _FindOneDb(redirection_domains=[
            {"domain": "other.example.com", "domain_type": "prelander", "status": "active"},
        ])
        with pytest.raises(ValueError, match="not a registered"):
            await _validate_prelander_bindings(db, {"prelander_domain": "missing.example.com"})

    async def test_anchor_domain_rejected_for_prelander_binding(self):
        from app.routers.landing_page_router import _validate_prelander_bindings

        db = _FindOneDb(redirection_domains=[
            {"domain": "anchor.example.com", "domain_type": "anchor", "status": "active"},
        ])
        with pytest.raises(ValueError, match="not a registered"):
            await _validate_prelander_bindings(db, {"prelander_domain": "anchor.example.com"})


@pytest.mark.asyncio
class TestInactiveDomainExcludedFromPool:
    async def test_paused_prelander_never_picked(self):
        """
        The pool include/exclude rule: routing must never send traffic to a
        paused prelander domain, even when it is the only pool entry and a
        landing page binds it.
        """
        from app.services.domain_service import select_active_prelander

        db = MagicMock()
        docs = [
            {"domain": "paused.example.com", "domain_type": "prelander", "status": "paused", "weight": 100},
            {"domain": "live.example.com", "domain_type": "prelander", "status": "active", "weight": 10},
        ]
        db.redirection_domains.find = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=docs)
        ))
        pool = ["paused.example.com", "live.example.com"]
        for _ in range(25):
            assert await select_active_prelander(db, pool) == "live.example.com"

    async def test_all_paused_pool_returns_none(self):
        from app.services.domain_service import select_active_prelander

        db = MagicMock()
        docs = [
            {"domain": "p1.example.com", "domain_type": "prelander", "status": "paused", "weight": 100},
        ]
        db.redirection_domains.find = MagicMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=docs)
        ))
        assert await select_active_prelander(db, ["p1.example.com"]) is None