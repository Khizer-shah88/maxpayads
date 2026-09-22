"""Domain assignment round trips and visitor rendering without external services."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from copy import deepcopy

import pytest
from bson import ObjectId
from starlette.requests import Request
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routers.prelander_router import _get_prelander_data
from app.routers.redirection_domain_router import create_redirection_domain, update_redirection_domain
from app.schemas.redirection_domain_schema import RedirectionDomainCreate, RedirectionDomainUpdate
from app.services.prelander_service import get_template_for_domain
from app.routers import prelander_template_router as templates_router


def matches(doc, query):
    for key, value in query.items():
        if isinstance(value, dict) and "$in" in value:
            if doc.get(key) not in value["$in"]:
                return False
        elif isinstance(value, dict) and "$nin" in value:
            if doc.get(key) in value["$nin"]:
                return False
        elif doc.get(key) != value:
            return False
    return True


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args):
        return self

    async def __aiter__(self):
        for doc in self.docs:
            yield dict(doc)


class Collection:
    def __init__(self, docs=()):
        self.docs = list(docs)

    async def find_one(self, query):
        for doc in self.docs:
            if matches(doc, query):
                return dict(doc)
        return None

    def find(self, query):
        return Cursor([doc for doc in self.docs if matches(doc, query)])

    async def update_many(self, query, update):
        for doc in self.docs:
            if matches(doc, query):
                doc.update(update["$set"])

    async def insert_one(self, doc):
        doc = {**doc, "_id": ObjectId()}
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    async def update_one(self, query, update):
        for doc in self.docs:
            if doc["_id"] == query["_id"]:
                doc.update(update["$set"])


@pytest.fixture
def db():
    templates = [
        {"_id": ObjectId(), "name": name, "os_type": os_type, "status": "active",
         "is_default": default, "full_html_template": f'<h1>{name}</h1><a href="{{Campaign_URL}}">Go</a><p>{{Password}}</p>'}
        for name, os_type, default in [
            ("Custom A", "both", False), ("Custom B", "both", False),
            ("Windows default", "windows", True), ("Mac default", "mac", True),
            ("Global default", "both", True),
        ]
    ]
    return SimpleNamespace(
        redirection_domains=Collection(), prelander_templates=Collection(templates),
        landing_pages=Collection(),
        campaigns=SimpleNamespace(find_one=AsyncMock(return_value={
            "name": "Campaign", "default_offer_url": "https://offer.example/download", "password": "test-password",
        })),
    )


async def add_domain(db, name="download.example", template_index=0, template="default"):
    result = await create_redirection_domain(
        RedirectionDomainCreate(domain=name, domain_type="prelander", template=template,
                                template_id=str(db.prelander_templates.docs[template_index]["_id"])),
        current_user={}, db=db,
    )
    return result["domain"]


async def test_distinct_domain_assignments_are_saved_and_rendered(db):
    for index in (0, 1):
        host = f"download{index}.example"
        domain = await add_domain(db, host, index)
        assert domain["template_id"] == str(db.prelander_templates.docs[index]["_id"])
        request = Request({"type": "http", "headers": [
            (b"host", b"backend.internal"), (b"x-prelander-host", host.encode()),
        ]})
        data = await _get_prelander_data(request, "windows", db, campaign_id=str(ObjectId()))
        assert data["template"]["id"] == domain["template_id"]
        assert f'<h1>Custom {"AB"[index]}</h1>' in data["rendered_html"]
        assert 'href="https://offer.example/download"' in data["rendered_html"]
        assert "test-password" in data["rendered_html"]
        assert "default</h1>" not in data["rendered_html"]


async def test_assignment_can_be_changed_preserved_and_cleared(db):
    domain = await add_domain(db)
    next_id = str(db.prelander_templates.docs[1]["_id"])
    changed = await update_redirection_domain(
        domain["id"], RedirectionDomainUpdate(template_id=next_id), current_user={}, db=db,
    )
    assert changed["domain"]["template_id"] == next_id
    selected = await get_template_for_domain(db, domain["domain"], os_hint="windows")
    assert selected["name"] == "Custom B"
    edited = await update_redirection_domain(
        domain["id"], RedirectionDomainUpdate(notes="Keep assignment"), current_user={}, db=db,
    )
    assert edited["domain"]["template_id"] == next_id
    cleared = await update_redirection_domain(
        domain["id"], RedirectionDomainUpdate(template_id=None), current_user={}, db=db,
    )
    assert cleared["domain"]["template_id"] is None
    selected = await get_template_for_domain(db, domain["domain"], os_hint="mac")
    assert selected["name"] == "Mac default"


@pytest.mark.parametrize("unavailable", ["paused", "archived", "deleted"])
@pytest.mark.parametrize("pinned_os, visitor_os, expected", [
    ("default", "mac", "Mac default"), ("default", "windows", "Windows default"),
    ("windows", "mac", "Windows default"), ("mac", "windows", "Mac default"),
])
async def test_unavailable_assignment_falls_back_by_os(db, unavailable, pinned_os, visitor_os, expected):
    domain = await add_domain(db, template=pinned_os)
    if unavailable == "deleted":
        db.prelander_templates.docs.pop(0)
    else:
        db.prelander_templates.docs[0]["status"] = unavailable
    selected = await get_template_for_domain(db, domain["domain"], os_hint=visitor_os)
    assert selected["name"] == expected


async def test_no_active_template_returns_builtin_fallback(db):
    domain = await add_domain(db)
    db.prelander_templates.docs.clear()
    request = Request({"type": "http", "headers": [(b"host", domain["domain"].encode())]})
    data = await _get_prelander_data(request, "windows", db, campaign_id=str(ObjectId()))
    assert data["success"] is True
    assert data["template"] is None
    assert data["offer_url"] == "https://offer.example/download"


def template_app(db, authenticated=True):
    app = FastAPI()
    app.include_router(templates_router.router)
    app.dependency_overrides[templates_router.get_db] = lambda: db
    if authenticated:
        app.dependency_overrides[templates_router.get_current_admin] = lambda: {"role": "admin"}
    return app


async def test_template_page_assignment_api_and_usage(db):
    first = await add_domain(db, "first.example", 0)
    second = await add_domain(db, "second.example", 1)
    third = await add_domain(db, "third.example", 1)
    # Legacy domain spelling and ObjectId references are still supported.
    db.redirection_domains.docs[0]["domain_type"] = "last"
    db.redirection_domains.docs[0]["template_id"] = ObjectId(first["template_id"])
    defaults_before = [t["is_default"] for t in db.prelander_templates.docs]
    tid = first["template_id"]
    async with AsyncClient(transport=ASGITransport(app=template_app(db)), base_url="http://test") as client:
        response = await client.put(f"/prelander-templates/{tid}/domains", json={
            "domain_ids": [first["id"], second["id"], second["id"]],
        })
        assert response.status_code == 200
        assert {d["domain"] for d in response.json()["assigned_domains"]} == {"first.example", "second.example"}
        for path in ("/prelander-templates", f"/prelander-templates/{tid}"):
            response = await client.get(path)
            assert response.status_code == 200
            payload = response.json()
            template = next(t for t in payload["templates"] if t["id"] == tid) if "templates" in payload else payload["template"]
            assert len(template["assigned_domains"]) == 2
            assert template["usage_count"] == 0  # Domain usage is separate from landing-page usage.
        # A non-default template now renders on the reassigned domain.
        request = Request({"type": "http", "headers": [(b"host", b"second.example")]})
        data = await _get_prelander_data(request, "windows", db, campaign_id=str(ObjectId()))
        assert "<h1>Custom A</h1>" in data["rendered_html"]
        # Clearing one template does not clear a different template's bindings.
        response = await client.put(f"/prelander-templates/{tid}/domains", json={"domain_ids": []})
        assert response.status_code == 200
        assert response.json()["assigned_domains"] == []
    assert (await get_template_for_domain(db, "second.example", "windows"))["name"] == "Windows default"
    assert (await get_template_for_domain(db, third["domain"], "windows"))["name"] == "Custom B"
    assert [t["is_default"] for t in db.prelander_templates.docs] == defaults_before


@pytest.mark.parametrize("invalid", ["malformed", "missing", "anchor", "inter"])
async def test_assignment_rejects_invalid_selection_before_writes(db, invalid):
    domain = await add_domain(db)
    if invalid in ("anchor", "inter"):
        bad_id = ObjectId()
        db.redirection_domains.docs.append({"_id": bad_id, "domain_type": invalid})
    else:
        bad_id = "not-an-object-id" if invalid == "malformed" else ObjectId()
    before = deepcopy(db.redirection_domains.docs)
    async with AsyncClient(transport=ASGITransport(app=template_app(db)), base_url="http://test") as client:
        response = await client.put(f'/prelander-templates/{domain["template_id"]}/domains', json={
            "domain_ids": [domain["id"], str(bad_id)],
        })
    assert response.status_code == 422
    assert db.redirection_domains.docs == before


async def test_assignment_requires_admin(db):
    async with AsyncClient(transport=ASGITransport(app=template_app(db, authenticated=False)), base_url="http://test") as client:
        response = await client.put(f'/prelander-templates/{db.prelander_templates.docs[0]["_id"]}/domains', json={"domain_ids": []})
    assert response.status_code == 401


async def test_assignment_rejects_missing_template(db):
    domain = await add_domain(db)
    before = deepcopy(db.redirection_domains.docs)
    async with AsyncClient(transport=ASGITransport(app=template_app(db)), base_url="http://test") as client:
        response = await client.put(f"/prelander-templates/{ObjectId()}/domains", json={"domain_ids": [domain["id"]]})
    assert response.status_code == 404
    assert db.redirection_domains.docs == before
