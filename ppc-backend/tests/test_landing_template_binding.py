"""
Landing Pages <-> Prelander Templates binding regressions.

Covers the connection the admin reported broken:

- Landing page create/update with prelander_domain + prelander_template_id
  writes template_id onto the redirection domain (Templates page reflects it).
- Assigning a template to domains from the Templates page writes back into the
  bound landing pages (reverse sync), and clears unassigned ones.
- The visitor renderer (get_template_for_domain) resolves the assigned
  template for the domain, falling back to the OS default.
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from test_publisher_stats_actions import Collection, matches

from app.dependencies import get_db, get_current_admin
from app.routers import landing_page_router
from app.services import prelander_service


PUB_DOMAIN = "prelander-show.example"
TEMPLATE_ID = ObjectId()


class DocsCollection:
    """find/filter over a plain doc list (subset of test Collection supports)."""

    def __init__(self, docs=()):
        self.docs = list(docs)

    def find(self, query=None, *args):
        rows = [d for d in self.docs if matches(d, query or {})]
        return SimpleNamespace(to_list=self._to_list(rows), sort=lambda *a, **k: self)

    def sort(self, *a, **k):
        return self

    def _to_list(self, rows):
        async def _to_list(length=None):
            return rows
        return _to_list

    def __aiter__(self):
        async def _gen(rows):
            for r in rows:
                yield r
        return _gen(self.docs)

    async def find_one(self, query=None, *args, **kwargs):
        query = query or {}
        for doc in self.docs:
            if matches(doc, query):
                return doc
        return None

    async def insert_one(self, doc):
        doc.setdefault("_id", ObjectId())
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    async def update_one(self, query, update):
        for doc in self.docs:
            if matches(doc, query):
                doc.update(update.get("$set", {}))
                doc.update({k: v for k, v in update.get("$unset", {}).items()})
                for k in update.get("$unset", {}):
                    doc.pop(k, None)
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    async def update_many(self, query, update):
        n = 0
        for doc in self.docs:
            if matches(doc, query):
                doc.update(update.get("$set", {}))
                for k in update.get("$unset", {}):
                    doc.pop(k, None)
                n += 1
        return SimpleNamespace(modified_count=n)

    async def delete_one(self, query):
        for i, doc in enumerate(self.docs):
            if matches(doc, query):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    async def count_documents(self, query=None):
        return len([d for d in self.docs if matches(d, query or {})])


def bind_app(db):
    app = FastAPI()
    app.include_router(landing_page_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_admin] = lambda: {"id": "admin", "role": "admin"}
    return app


def make_db():
    return SimpleNamespace(
        landing_pages=DocsCollection(),
        prelander_templates=DocsCollection([
            {"_id": TEMPLATE_ID, "name": "Dropbox Favicon Template", "status": "active",
             "os_type": "both", "title": "t", "subtitle": "s", "button_text": "c"},
        ]),
        redirection_domains=DocsCollection([
            {"_id": ObjectId(), "domain": PUB_DOMAIN, "domain_type": "prelander",
             "status": "active", "template": "default", "weight": 100},
        ]),
        campaigns=DocsCollection(), publishers=DocsCollection(), system_settings=DocsCollection(),
    )


async def test_landing_page_assignment_updates_domain_binding():
    """Create a landing page bound to a domain + template → the DOMAIN doc
    carries template_id (the Templates page + the visitor renderer read it)."""
    db = make_db()
    async with AsyncClient(transport=ASGITransport(app=bind_app(db)), base_url="https://portal.example") as client:
        res = await client.post("/landing-pages", json={
            "name": "Dropbox LP",
            "campaign_id": str(ObjectId()),
            "status": "active",
            "weight": 50,
            "prelander_domain": PUB_DOMAIN,
            "prelander_template_id": str(TEMPLATE_ID),
        })
        assert res.status_code == 201, res.text

    domain = db.redirection_domains.docs[0]
    assert str(domain.get("template_id")) == str(TEMPLATE_ID), domain


async def test_landing_page_update_clearing_template_unsets_binding():
    """Updating the page's template to None clears the domain binding."""
    db = make_db()
    db.redirection_domains.docs[0]["template_id"] = str(TEMPLATE_ID)
    page_id = ObjectId()
    db.landing_pages.docs.append({
        "_id": page_id, "name": "LP", "campaign_id": str(ObjectId()),
        "status": "active", "weight": 50,
        "prelander_domain": PUB_DOMAIN,
        "prelander_template_id": str(TEMPLATE_ID),
    })
    async with AsyncClient(transport=ASGITransport(app=bind_app(db)), base_url="https://portal.example") as client:
        res = await client.put(f"/landing-pages/{page_id}", json={"prelander_template_id": None})
        assert res.status_code == 200, res.text

    domain = db.redirection_domains.docs[0]
    assert domain.get("template_id") in (None, ""), domain


async def test_get_template_for_domain_resolves_assignment():
    """The visitor renderer must pick the domain's assigned template."""
    db = make_db()
    db.redirection_domains.docs[0]["template_id"] = str(TEMPLATE_ID)

    tpl = await prelander_service.get_template_for_domain(db, PUB_DOMAIN, os_hint="windows")
    assert tpl is not None
    assert str(tpl["_id"]) == str(TEMPLATE_ID)


async def test_get_template_for_domain_falls_back_to_os_default():
    """An unassigned active domain serves the OS Default Template — here none
    is active, so the lookup returns None and the page renders the built-in."""
    db = make_db()
    tpl = await prelander_service.get_template_for_domain(db, PUB_DOMAIN, os_hint="windows")
    assert tpl is None  # no is_default template exists in the fake


async def test_one_domain_one_landing_page_uniqueness():
    """A second page cannot bind an already-bound domain (400)."""
    db = make_db()
    page_id = ObjectId()
    db.landing_pages.docs.append({
        "_id": page_id, "name": "LP One", "campaign_id": str(ObjectId()),
        "status": "active", "weight": 50,
        "prelander_domain": PUB_DOMAIN,
        "prelander_template_id": str(TEMPLATE_ID),
    })
    async with AsyncClient(transport=ASGITransport(app=bind_app(db)), base_url="https://portal.example") as client:
        res = await client.post("/landing-pages", json={
            "name": "LP Two",
            "campaign_id": str(ObjectId()),
            "status": "active",
            "weight": 50,
            "prelander_domain": PUB_DOMAIN,
            "prelander_template_id": str(TEMPLATE_ID),
        })
    assert res.status_code == 400
    assert "already bound" in res.text