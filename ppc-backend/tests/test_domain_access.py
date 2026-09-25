"""Public traffic only works on its assigned host, through API and browser gates."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.services.domain_access_service import allow_path, domain_role, validate_stats_domain
from app.services.domain_service import create_domain
from test_publisher_stats_actions import Collection


@pytest.fixture
def domains_db(monkeypatch):
    monkeypatch.setattr(settings, 'PORTAL_HOSTNAMES', 'portal.example')
    return SimpleNamespace(
        redirection_domains=Collection([
            {'domain': f'{role}.example', 'domain_type': role, 'status': 'active'}
            for role in ('anchor', 'inter', 'prelander')
        ]),
        system_settings=Collection([{'key': 'stats_domain', 'value': 'stats.example'}]),
        direct_links=Collection([
            {'stats_share_id': 'global-share', 'publisher_id': 'one', 'status': 'active'},
            {'stats_share_id': 'custom-share', 'publisher_id': 'two', 'status': 'active', 'stats_domain': 'custom.example'},
        ]),
    )


@pytest.mark.parametrize('host', ['portal', 'anchor', 'inter', 'prelander', 'stats', 'unknown'])
@pytest.mark.parametrize('path,allowed', [
    ('/admin/dashboard', {'portal'}),
    ('/api/admin/publishers', {'portal'}),
    ('/click', {'anchor'}),
    ('/ad.js', {'anchor'}),
    ('/go', {'anchor'}),
    ('/d/h_ticket', {'inter', 'prelander'}),
    ('/api/prelander/hop/h_ticket', {'inter'}),
    ('/api/prelander/resolve/session', {'prelander'}),
    ('/_auth/ticket', {'prelander'}),
    ('/public-stats/global-share', {'stats'}),
    ('/api/public-stats/global-share', {'stats'}),
    ('/_next/static/chunk.js', {'portal', 'anchor', 'inter', 'prelander', 'stats'}),
])
async def test_role_matrix(domains_db, host, path, allowed):
    assert bool(await allow_path(domains_db, f'{host}.example', path)) == (host in allowed)


async def test_custom_share_only_works_on_assigned_domain(domains_db):
    assert await allow_path(domains_db, 'custom.example', '/public-stats/custom-share') == 'stats'
    for host in ('stats.example', 'portal.example', 'prelander.example', 'unknown.example'):
        assert await allow_path(domains_db, host, '/public-stats/custom-share') is None
    assert await allow_path(domains_db, 'custom.example', '/public-stats/global-share') is None
    domains_db.direct_links.docs[1]['stats_domain'] = 'replacement.example'
    assert await allow_path(domains_db, 'custom.example', '/public-stats/custom-share') is None
    assert await allow_path(domains_db, 'replacement.example', '/public-stats/custom-share') == 'stats'


async def test_paused_or_deleted_domain_loses_access_immediately(domains_db):
    domains_db.redirection_domains.docs[0]['status'] = 'paused'
    assert await allow_path(domains_db, 'anchor.example', '/click') is None
    domains_db.redirection_domains.docs.clear()
    assert await allow_path(domains_db, 'inter.example', '/d/h_ticket') is None


async def test_domain_roles_cannot_overlap(domains_db):
    for host in ('portal.example', 'anchor.example', 'inter.example', 'prelander.example'):
        with pytest.raises(ValueError):
            await validate_stats_domain(domains_db, host)
    for host in ('portal.example', 'stats.example', 'custom.example'):
        with pytest.raises(ValueError):
            await create_domain(domains_db, {'domain': host, 'domain_type': 'anchor'})
    assert await validate_stats_domain(domains_db, 'HTTPS://New.Example/') == 'new.example'


async def test_direct_api_cannot_bypass_with_forwarded_or_prelander_host(domains_db, monkeypatch):
    from app.middleware import domain_access_middleware as guard
    monkeypatch.setattr(guard, 'get_database', lambda: domains_db)
    app = FastAPI()
    app.add_middleware(guard.DomainAccessMiddleware)

    @app.get('/click')
    async def click():
        return {'accepted': True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://stats.example') as client:
        denied = await client.get('/click', headers={
            'x-forwarded-host': 'anchor.example', 'x-prelander-host': 'anchor.example',
        })
        assert denied.status_code == 404 and denied.content == b''
        assert (await client.get('/click', headers={'host': 'anchor.example'})).status_code == 200


async def test_legacy_stats_domain_spelling_is_recognized(domains_db):
    domains_db.direct_links.docs[1]['stats_domain'] = 'https://custom.example/'
    assert await domain_role(domains_db, 'custom.example') == 'stats'
