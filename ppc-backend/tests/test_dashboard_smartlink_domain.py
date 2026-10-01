"""Dashboard domain changes must affect the domains used by link generators."""
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.cache import redis_client
from app.config import settings
from app.dependencies import get_current_admin, get_db
from app.routers import admin_router, publisher_router, smartlink_structure_router
from app.services.domain_service import resolve_domain_url, update_domain
from app.services.domain_access_service import allow_path
from app.services.smartlink_service import generate_embed_code_with_smartlink
from test_domain_routing_flow import Collection as FlowCollection, domain
from test_prelander_auth import FakeRedis


class Collection(FlowCollection):
    async def insert_one(self, doc):
        stored = deepcopy(doc)
        stored.setdefault('_id', ObjectId())
        self.docs.append(stored)
        return SimpleNamespace(inserted_id=stored['_id'])

    async def update_one(self, query, update, upsert=False):
        if not await self.find_one(query) and upsert:
            await self.insert_one(query)
        await super().update_one(query, update)


@pytest.fixture
def dashboard(monkeypatch):
    monkeypatch.setattr(settings, 'CLICK_HOT_CACHE', True)
    monkeypatch.setattr(settings, 'PORTAL_HOSTNAMES', 'portal.example')
    redis = FakeRedis()
    monkeypatch.setattr(redis_client, 'get_redis', lambda: redis)
    publisher = {'_id': ObjectId(), 'public_id': 'publisher123', 'publisher_type': 'manual'}
    db = SimpleNamespace(
        redirection_domains=Collection([domain('old.example', 'anchor', is_default=True)]),
        system_settings=Collection([{'key': 'platform_domain', 'value': 'https://old.example'}]),
        publishers=Collection([publisher]), websites=Collection(), direct_links=Collection(),
        smartlink_structures=Collection([{'_id': ObjectId(), 'name': 'Default', 'is_default': True,
            'status': 'active', 'publisher_param': 'tag', 'website_param': 'sid', 'include_website': True}]),
    )
    app = FastAPI()
    app.include_router(admin_router.router)
    app.include_router(smartlink_structure_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_admin] = lambda: {'id': 'admin'}
    return db, redis, app, str(publisher['_id'])


@pytest.mark.parametrize('existing', [False, True])
async def test_dashboard_save_changes_all_generated_domains(dashboard, existing):
    db, redis, app, publisher_id = dashboard
    if existing:
        db.redirection_domains.docs.append(domain('new.example', 'anchor', status='paused'))
    assert await resolve_domain_url(db, 'anchor', publisher_id, redis=redis) == 'https://old.example'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://portal.example') as client:
        saved = await client.put('/admin/domain', json={'domain': 'HTTPS://NEW.EXAMPLE/'})
        assert saved.status_code == 200, saved.text
        assert saved.json()['domain'] == 'https://new.example'
        assert (await client.get('/admin/domain')).json()['domain'] == 'https://new.example'
        links = await client.get(f'/admin/publishers/{publisher_id}/smartlink')
        assert urlsplit(links.json()['smartlink']).hostname == 'new.example'
        structured = await client.post('/admin/smartlink-structures/generate', json={'publisher_id': 'publisher123'})
        assert urlsplit(structured.json()['smartlink']).hostname == 'new.example'

    assert await resolve_domain_url(db, 'anchor', publisher_id, redis=redis) == 'https://new.example'
    assert await allow_path(db, 'new.example', '/click', redis=redis) == 'anchor'
    assert len([d for d in db.redirection_domains.docs if d.get('is_default')]) == 1
    # Existing published URLs remain assigned to the old active Anchor.
    assert await allow_path(db, 'old.example', '/click') == 'anchor'
    request = Request({'type': 'http', 'scheme': 'https', 'server': ('portal.example', 443), 'headers': []})
    base = await publisher_router._get_base_url(db, request, publisher_id)
    tracking = await publisher_router._get_tracking_url(db, publisher_id)
    codes = await generate_embed_code_with_smartlink(db, publisher_id, 'site', base, tracking, use_public_ids=False)
    assert urlsplit(codes['smart_link']).hostname == 'new.example'
    assert 'https://new.example/ad.js?' in codes['embed_code']


@pytest.mark.parametrize('value', ['', 'not a domain', 'https://portal.example', 'https://inter.example', 'javascript:alert(1)'])
async def test_invalid_dashboard_domain_does_not_change_links(dashboard, value):
    db, _, app, _ = dashboard
    db.redirection_domains.docs.append(domain('inter.example', 'inter'))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://portal.example') as client:
        response = await client.put('/admin/domain', json={'domain': value})
        assert response.status_code == 400
    assert await resolve_domain_url(db, 'anchor') == 'https://old.example'
    assert (await db.system_settings.find_one({'key': 'platform_domain'}))['value'] == 'https://old.example'


async def test_dashboard_displays_actual_anchor_and_preserves_publisher_override(dashboard):
    db, redis, app, publisher_id = dashboard
    db.system_settings.docs[0]['value'] = 'https://stale.example'
    db.redirection_domains.docs.append(domain('assigned.example', 'anchor', publisher_ids=[publisher_id]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://portal.example') as client:
        assert (await client.get('/admin/domain')).json()['domain'] == 'https://old.example'
        assert (await client.put('/admin/domain', json={'domain': 'new.example'})).status_code == 200
    assert await resolve_domain_url(db, 'anchor', publisher_id, redis=redis) == 'https://assigned.example'
    assert await resolve_domain_url(db, 'anchor', 'other', redis=redis) == 'https://new.example'
    # Editing the same default from Redirection Domains stays in sync too.
    saved = await db.redirection_domains.find_one({'domain': 'new.example'})
    await update_domain(db, str(saved['_id']), {'domain': 'renamed.example'})
    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://portal.example') as client:
        assert (await client.get('/admin/domain')).json()['domain'] == 'https://renamed.example'
