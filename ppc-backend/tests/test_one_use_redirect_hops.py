"""Exercise the actual ticket store and all configured hops, including replay races."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.dependencies import get_db
from app.services import prelander_auth_service as auth
from app.services.redirect_hop_service import advance_hop
from app.services.redirect_pipeline import RedirectResolutionContext, stage_authorize_prelander
from test_prelander_auth import FakeRedis
from test_publisher_stats_actions import Collection


async def routed_click(monkeypatch, bypass=False, **context):
    monkeypatch.setattr(settings, 'PORTAL_HOSTNAMES', 'portal.example')
    db = SimpleNamespace(
        redirection_domains=Collection([
            {'domain': host, 'domain_type': role, 'status': 'active'} for host, role in (
                ('inter.example', 'inter'), ('extra.example', 'inter'), ('last.example', 'prelander'),
            )
        ]),
        # domain_role falls back to stats lookups when no redirection role
        # matches (e.g. a paused host) — those collections must exist.
        system_settings=Collection(),
        direct_links=Collection(),
    )
    redis = FakeRedis()
    ctx = RedirectResolutionContext(raw_pub='PUB_123', raw_site=None, ip='1.2.3.4', user_agent='Browser')
    ctx.click_id = 'click-1'
    ctx.destination_url = 'https://inter.example/d/encrypted-original'
    ctx.prelander_url = 'https://last.example'
    ctx.redirect_chain = {'_id': ObjectId(), 'extra_domains': ['extra.example'], 'cookie_lifetime': 30}
    ctx.skip_prelander = bypass
    ctx.bypass_url = 'https://campaign.example/download' if bypass else None
    for name, value in context.items():
        setattr(ctx, name, value)
    await stage_authorize_prelander(ctx, db, redis)
    return db, redis, ctx


def token(url):
    return url.rsplit('/', 1)[-1]


async def test_full_chain_consumes_each_inter_then_final_handoff(monkeypatch):
    from app.routers import prelander_router as router
    db, redis, ctx = await routed_click(monkeypatch)
    session = await auth.get_session(ctx.prelander_auth_token, redis)
    assert 1795 <= session.expires_at - int(time.time()) <= 1800
    assert ctx.destination_url.startswith('https://inter.example/d/h_')
    extra = await advance_hop(redis, db, token(ctx.destination_url), 'inter.example', '1.2.3.4', 'Browser')
    assert extra.startswith('https://extra.example/d/h_')
    assert await advance_hop(redis, db, token(ctx.destination_url), 'inter.example', '1.2.3.4', 'Browser') is None
    final = await advance_hop(redis, db, token(extra), 'extra.example', '1.2.3.4', 'Browser')
    assert final.startswith('https://last.example/_auth/')
    assert await advance_hop(redis, db, token(extra), 'extra.example', '1.2.3.4', 'Browser') is None

    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(router, 'get_redis_safe', lambda: redis)
    monkeypatch.setattr(router, '_get_prelander_data', AsyncMock(return_value={'success': True}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://last.example', headers={'user-agent': 'Browser'}) as client:
        path = '/prelander' + urlparse(final).path
        arrival = await client.get(path)
        assert arrival.status_code == 302 and arrival.headers['location'] == '/?_s=1'
        assert auth.PL_SESSION_COOKIE in arrival.cookies
        assert (await client.get(path)).status_code == 403
        assert (await client.get('/prelander/session-check')).status_code == 200
        assert (await client.get('/prelander/resolve/session')).json()['success']
        assert (await client.get('/prelander/resolve/session', headers={'host': 'different.example'})).status_code == 403


async def test_concurrent_replay_only_one_request_advances(monkeypatch):
    db, redis, ctx = await routed_click(monkeypatch)
    results = await asyncio.gather(*[
        advance_hop(redis, db, token(ctx.destination_url), 'inter.example', '1.2.3.4', 'Browser')
        for _ in range(10)
    ])
    assert sum(result is not None for result in results) == 1


@pytest.mark.parametrize('failure', ['wrong-host', 'wrong-browser', 'expired', 'paused-next', 'revoked'])
async def test_ticket_cannot_be_used_outside_its_flow(monkeypatch, failure):
    db, redis, ctx = await routed_click(monkeypatch)
    host, ua = 'inter.example', 'Browser'
    if failure == 'wrong-host':
        host = 'extra.example'
    elif failure == 'wrong-browser':
        ua = 'Other Browser'
    elif failure == 'expired':
        key = 'redirect_hop:' + token(ctx.destination_url)
        value, _ = redis.store[key]
        redis.store[key] = (value, time.time() - 1)
    elif failure == 'paused-next':
        db.redirection_domains.docs[1]['status'] = 'paused'
    else:
        await auth.revoke_authorization(ctx.prelander_auth_token, redis)
    assert await advance_hop(redis, db, token(ctx.destination_url), host, '1.2.3.4', ua) is None


async def test_bypass_still_uses_one_inter_ticket(monkeypatch):
    db, redis, ctx = await routed_click(monkeypatch, bypass=True)
    destination = await advance_hop(redis, db, token(ctx.destination_url), 'inter.example', '1.2.3.4', 'Browser')
    assert destination == 'https://campaign.example/download'
    assert await advance_hop(redis, db, token(ctx.destination_url), 'inter.example', '1.2.3.4', 'Browser') is None


@pytest.mark.parametrize('os_name,expected_os', [('Mac OS X', 'mac'), ('Windows 10', 'windows'), ('iOS', 'mac')])
async def test_delayed_arrival_renders_selected_destination_and_template(monkeypatch, os_name, expected_os):
    """Exercise hops, cookie exchange, claim and real rendering with domain policy enabled."""
    from app.routers import prelander_router as router
    from app.middleware import domain_access_middleware as gate

    campaign_id, template_id = ObjectId(), ObjectId()
    selected_url = 'https://selected.example/device-specific'
    db, redis, ctx = await routed_click(monkeypatch, os_name=os_name,
        campaign_id=str(campaign_id), offer_url=selected_url)
    db.redirection_domains.docs[-1]['template_id'] = str(template_id)
    db.campaigns = Collection([{'_id': campaign_id, 'name': 'Selected campaign',
        'default_offer_url': 'https://wrong.example/fallback', 'password': 'test-password'}])
    db.prelander_templates = Collection([{'_id': template_id, 'status': 'active', 'name': 'Assigned',
        'full_html_template': '<h1>Assigned template</h1><a href="{Campaign_URL}">Continue</a>'}])
    db.landing_pages = Collection()
    monkeypatch.setattr(router, 'get_redis_safe', lambda: redis)
    monkeypatch.setattr(gate, 'get_database', lambda: db)
    monkeypatch.setattr(gate, 'get_redis', lambda: redis)
    app = FastAPI()
    app.add_middleware(gate.DomainAccessMiddleware)
    app.include_router(router.router)
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), headers={'user-agent': 'Browser'}) as client:
        destination = ctx.destination_url
        for host in ('inter.example', 'extra.example'):
            hop = await client.post(f'https://{host}/prelander/hop/{token(destination)}')
            assert hop.status_code == 200
            destination = hop.json()['next_url']
        arrival = await client.get('https://last.example/prelander' + urlparse(destination).path)
        assert arrival.status_code == 302
        assert arrival.headers['location'] == '/d/session'
        # Backgrounded tabs and slower networks can take over 20 seconds.
        now = time.time()
        monkeypatch.setattr(time, 'time', lambda: now + 30)
        claim = await client.get('https://last.example/prelander/claim')
        assert claim.status_code == 200
        assert claim.headers['cache-control'] == 'no-store, private'
        for _ in range(3):
            response = await client.get('https://last.example/prelander/resolve/session')
            assert response.status_code == 200
            data = response.json()
            assert data['offer_url'] == selected_url
            assert data['os'] == expected_os
            assert data['template']['id'] == str(template_id)
            assert selected_url in data['rendered_html']
            assert 'wrong.example' not in data['rendered_html']
        # Refreshing uses the cookie; neither handoffs nor arrivals become reusable.
        assert (await client.get('https://last.example/prelander/claim')).status_code == 403
