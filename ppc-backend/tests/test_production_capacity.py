"""Regressions for the site-wide failure after ~200 internal checks."""
import asyncio
from collections import Counter
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.exceptions import NoScriptError

from app.config import settings
from app.middleware.capacity import CapacityMiddleware
from app.middleware.domain_access_middleware import DomainAccessMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security_middleware import SecurityMiddleware
from test_publisher_stats_actions import Collection


class CountingRedis:
    def __init__(self):
        self.counts = Counter()
        self.loaded = False

    async def evalsha(self, sha, count, key, window):
        if not self.loaded:
            raise NoScriptError()
        self.counts[key] += 1
        return self.counts[key]

    async def eval(self, script, count, key, window):
        self.loaded = True
        return await self.evalsha('', count, key, window)


@pytest.fixture
def app_and_store(monkeypatch):
    from app.cache import redis_client
    from app.middleware import domain_access_middleware
    store = CountingRedis()
    monkeypatch.setattr(redis_client, 'get_redis', lambda: store)
    monkeypatch.setattr(settings, 'PORTAL_HOSTNAMES', 'portal.example')
    monkeypatch.setattr(settings, 'REQUESTS_PER_IP_PER_MINUTE', 200)
    monkeypatch.setattr(settings, 'TRUSTED_PROXY_CIDRS', '172.20.0.0/24')
    db = SimpleNamespace(
        redirection_domains=Collection([{'domain': 'anchor.example', 'domain_type': 'anchor', 'status': 'active'}]),
        system_settings=Collection([]), direct_links=Collection([]),
    )
    monkeypatch.setattr(domain_access_middleware, 'get_database', lambda: db)
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CapacityMiddleware)
    app.add_middleware(DomainAccessMiddleware)

    @app.get('/admin/dashboard')
    async def dashboard():
        return {'ok': True}

    @app.get('/click')
    async def click():
        return {'ok': True}

    @app.get('/health')
    async def health():
        return {'ok': True}

    return app, store, db


async def test_5000_domain_probes_do_not_consume_user_quota(app_and_store):
    app, store, _ = app_and_store
    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://portal.example') as client:
        # Bounded batches reproduce the previous 200/minute ceiling.
        for _ in range(20):
            responses = await asyncio.gather(*(client.get('/domain-access?path=/admin/auth') for _ in range(250)))
            assert all(r.status_code == 200 and r.json()['role'] == 'portal' for r in responses)
        assert not store.counts
        assert (await client.get('/admin/dashboard')).status_code == 200


async def test_one_visitor_cannot_exhaust_another_or_internal_probes(app_and_store):
    app, store, _ = app_and_store
    async with AsyncClient(transport=ASGITransport(app=app, client=('172.20.0.3', 1234)), base_url='https://portal.example') as c:
        for _ in range(200):
            assert (await c.get('/admin/dashboard', headers={'x-real-ip': '203.0.113.1'})).status_code == 200
        limited = await c.get('/admin/dashboard', headers={'x-real-ip': '203.0.113.1'})
        assert limited.status_code == 429 and limited.headers['retry-after'] == '60'
        assert (await c.get('/admin/dashboard', headers={'x-real-ip': '203.0.113.2'})).status_code == 200
        assert (await c.get('/domain-access?path=/admin/dashboard')).status_code == 200
        # Redis SCRIPT FLUSH must not silently disable the limiter.
        store.loaded = False
        assert (await c.get('/admin/dashboard', headers={'x-real-ip': '203.0.113.1'})).status_code == 429


async def test_untrusted_forwarded_ip_cannot_reset_quota(app_and_store):
    app, store, _ = app_and_store
    async with AsyncClient(transport=ASGITransport(app=app, client=('198.51.100.10', 1234)), base_url='https://portal.example') as c:
        await c.get('/admin/dashboard', headers={'x-real-ip': '203.0.113.1'})
        await c.get('/admin/dashboard', headers={'x-real-ip': '203.0.113.2'})
    assert store.counts == {'req_rate:198.51.100.10': 2}


async def test_domain_decisions_do_not_leak_between_paths_or_survive_disable(app_and_store):
    app, _, db = app_and_store
    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://anchor.example') as c:
        assert (await c.get('/click')).status_code == 200
        assert (await c.get('/admin/dashboard')).status_code == 404
        assert (await c.get('/click')).status_code == 200
        assert (await c.get('/domain-access', headers={'x-original-uri': '/admin/dashboard'})).status_code == 403
        db.redirection_domains.docs[0]['status'] = 'paused'
        assert (await c.get('/click')).status_code == 404


async def test_capacity_limit_recovers_and_does_not_block_health(app_and_store, monkeypatch):
    app, _, _ = app_and_store
    monkeypatch.setattr(settings, 'API_MAX_INFLIGHT', 1)
    entered, release = asyncio.Event(), asyncio.Event()

    @app.get('/slow')
    async def slow():
        entered.set()
        await release.wait()
        return {'ok': True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://portal.example') as c:
        running = asyncio.create_task(c.get('/slow'))
        await entered.wait()
        assert (await c.get('/admin/dashboard')).status_code == 503
        assert (await c.get('/health')).status_code == 200
        assert (await c.get('/domain-access?path=/admin/auth')).status_code == 200
        release.set()
        assert (await running).status_code == 200
        assert (await c.get('/admin/dashboard')).status_code == 200


async def test_security_layer_preserves_stream_and_multiple_cookies():
    from starlette.responses import StreamingResponse
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.get('/stream')
    async def stream():
        async def chunks():
            yield b'first'
            await asyncio.sleep(0)
            yield b'second'
        response = StreamingResponse(chunks())
        response.set_cookie('mpa_pls', 'session')
        response.set_cookie('mpa_tab_ok', 'bridge')
        return response

    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://portal.example') as c:
        response = await c.get('/stream')
        assert response.content == b'firstsecond'
        cookies = response.headers.get_list('set-cookie')
        assert len(cookies) == 2
        assert 'HttpOnly' in cookies[0] and 'HttpOnly' not in cookies[1]
        assert all('Secure' in cookie for cookie in cookies)
        assert response.headers['x-request-id']
        assert (await c.get('/stream', headers={'content-length': 'bad'})).status_code == 400
        assert (await c.get('/stream', headers={'x-api-key': 'bad'})).status_code == 401


async def test_slow_password_verification_does_not_block_other_requests(monkeypatch):
    import threading
    from unittest.mock import AsyncMock
    from app.routers import auth_router
    from app.schemas.auth_schema import LoginRequest

    started, release = threading.Event(), threading.Event()

    def slow_verify(*args):
        started.set()
        assert release.wait(2), 'Password verification blocked the event loop'
        return True

    monkeypatch.setattr(auth_router, 'verify_password', slow_verify)
    monkeypatch.setattr(auth_router, 'get_publisher_by_email', AsyncMock(return_value={
        'id': 'admin-id', 'name': 'Admin', 'email': 'admin@example.com', 'role': 'admin',
    }))
    db = SimpleNamespace(publishers=SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1))))
    task = asyncio.create_task(auth_router.login(LoginRequest(email='admin@example.com', password='password'), db=db))
    try:
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(.01)
        assert started.is_set()
        release.set()
        assert (await task).role == 'admin'
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_slow_broker_publish_does_not_block_the_event_loop(monkeypatch):
    import threading
    from app.services import redirect_pipeline as pipeline
    from app.tasks.click_tasks import process_click
    from test_redirect_pipeline import make_ctx

    started, release = threading.Event(), threading.Event()

    def slow_publish(*args):
        started.set()
        assert release.wait(2), 'Broker publishing blocked the event loop'

    monkeypatch.setattr(process_click, 'delay', slow_publish)
    ctx = make_ctx()
    ctx.click_document = {'publisher_id': 'publisher'}
    task = asyncio.create_task(pipeline.stage_resolve_cpc(ctx, db=None))
    try:
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(.01)
        assert started.is_set()
        release.set()
        await task
        assert ctx.trace[-1].outcome == 'deferred_to_task'
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
