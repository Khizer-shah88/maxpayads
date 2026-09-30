"""Route selection through one-use hops, with the production cache enabled."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse

import pytest
from bson import ObjectId

from app.config import settings
from app.services import domain_service as domains, traffic_router as routing
from app.services.redirect_pipeline import RedirectResolutionContext, stage_authorize_prelander
from app.services.redirect_hop_service import advance_hop
from app.services.domain_access_service import domain_role
from test_prelander_auth import FakeRedis


def matches(doc, query):
    for key, value in query.items():
        if key == '$or':
            if not any(matches(doc, item) for item in value):
                return False
            continue
        actual = doc.get(key)
        if isinstance(value, dict):
            for op, operand in value.items():
                if op == '$in' and actual not in operand: return False
                if op == '$ne' and actual == operand: return False
                if op == '$size' and (not isinstance(actual, list) or len(actual) != operand): return False
                if op == '$exists' and (key in doc) != operand: return False
        elif isinstance(actual, list):
            if value not in actual: return False
        elif actual != value:
            return False
    return True


class Cursor:
    def __init__(self, docs): self.docs = deepcopy(docs)
    async def to_list(self, length=None): return self.docs[:length]
    def __aiter__(self):
        async def iterate():
            for doc in self.docs: yield doc
        return iterate()


class Collection:
    def __init__(self, docs=()): self.docs = list(docs)
    def find(self, query, *args): return Cursor([d for d in self.docs if matches(d, query)])
    async def find_one(self, query, *args, **kwargs):
        docs = self.find(query).docs
        return docs[0] if docs else None
    async def update_one(self, query, update, **kwargs):
        for doc in self.docs:
            if matches(doc, query):
                doc.update(update.get('$set', {}))
                return
    async def update_many(self, query, update):
        for doc in self.docs:
            if matches(doc, query): doc.update(update.get('$set', {}))


def domain(host, role, **fields):
    return {'_id': ObjectId(), 'domain': host, 'domain_type': role,
            'status': 'active', 'publisher_ids': [], 'weight': 100, **fields}


@pytest.fixture
def flow(monkeypatch):
    from app.services import targeting_engine as targeting
    monkeypatch.setattr(settings, 'CLICK_HOT_CACHE', True)
    monkeypatch.setattr(settings, 'PORTAL_HOSTNAMES', 'portal.example')
    campaign_id = ObjectId()
    monkeypatch.setattr(targeting, 'resolve_campaign_for_click', AsyncMock(return_value=str(campaign_id)))
    monkeypatch.setattr(targeting.TargetingEngine, 'resolve_destination', AsyncMock(
        return_value=('https://offer.example/download', False, {'rule_type': 'default'})))
    db = SimpleNamespace(
        campaigns=Collection([{'_id': campaign_id, 'direct_redirect_mode': False}]),
        offers=Collection(), landing_pages=Collection(), system_settings=Collection(),
        direct_links=Collection(), publishers=Collection(), redirect_chains=Collection(),
        redirection_domains=Collection([
            domain('anchor.example', 'anchor'), domain('inter.example', 'inter'),
            domain('one.example', 'prelander'), domain('two.example', 'prelander'),
        ]),
    )
    return db, FakeRedis()


async def start(flow, publisher='publisher-1', host='anchor.example'):
    db, redis = flow
    ctx = RedirectResolutionContext(request_host=host, ip='203.0.113.10', user_agent='Browser')
    ctx.click_id, ctx.publisher_id, ctx.os_name = str(ObjectId()), publisher, 'Windows'
    ctx.destination_url, _ = await routing.route_click(
        {'publisher_id': publisher, 'os': 'Windows', 'country_code': 'US'}, db, redis, ctx)
    await stage_authorize_prelander(ctx, db, redis)
    return ctx


async def follow(flow, ctx):
    db, redis = flow
    url, hosts = ctx.destination_url, []
    while '/d/h_' in url:
        host = urlparse(url).hostname
        assert host not in hosts, 'redirect loop'
        hosts.append(host)
        url = await advance_hop(redis, db, url.rsplit('/', 1)[-1], host, ctx.ip, ctx.user_agent)
        assert url, f'flow stopped at {host}'
    return hosts, url


async def test_default_pool_weights_apply_on_each_click_even_with_cache(flow, monkeypatch):
    monkeypatch.setattr('random.uniform', lambda low, high: 0)
    first = await start(flow)
    monkeypatch.setattr('random.uniform', lambda low, high: high)
    second = await start(flow)
    assert first.prelander_url == 'https://one.example'
    assert second.prelander_url == 'https://two.example'
    for ctx in (first, second):
        hosts, url = await follow(flow, ctx)
        assert hosts == ['inter.example']
        assert url.startswith(ctx.prelander_url + '/_auth/')


async def test_zero_weight_default_does_not_receive_traffic(flow):
    db, _ = flow
    db.redirection_domains.docs[2].update(is_default=True, weight=0)
    assert (await start(flow)).prelander_url == 'https://two.example'


async def test_default_pool_never_borrows_another_publishers_assignment(flow):
    db, _ = flow
    for doc in db.redirection_domains.docs[2:]: doc['publisher_ids'] = ['other-publisher']
    ctx = await start(flow)
    assert ctx.destination_url == 'https://offer.example/download'


async def test_inter_without_prelander_does_not_issue_a_dead_end_ticket(flow):
    db, _ = flow
    db.redirection_domains.docs = db.redirection_domains.docs[:2]
    ctx = await start(flow)
    assert ctx.destination_url == 'https://offer.example/download'


@pytest.mark.parametrize('extra_count', [0, 1, 3])
@pytest.mark.parametrize('bypass', [False, True])
async def test_chain_keeps_exact_order_and_pool_across_publishers(flow, extra_count, bypass):
    db, _ = flow
    extras = [f'extra-{n}.example' for n in range(extra_count)]
    db.redirection_domains.docs += [domain(h, 'inter') for h in extras]
    db.redirect_chains.docs.append({'_id': ObjectId(), 'anchor_domain': 'anchor.example',
        'inter_domain': 'inter.example', 'extra_domains': extras,
        'prelander_pool': ['two.example'], 'status': 'active'})
    db.campaigns.docs[0]['direct_redirect_mode'] = bypass
    for publisher in ('publisher-1', 'publisher-2'):
        ctx = await start(flow, publisher)
        hosts, url = await follow(flow, ctx)
        assert hosts == ['inter.example'] + ([] if bypass else extras)
        assert url == 'https://offer.example/download' if bypass else url.startswith('https://two.example/_auth/')


async def test_empty_chain_pool_cannot_fall_through_to_global_pool(flow):
    db, _ = flow
    db.redirect_chains.docs.append({'_id': ObjectId(), 'anchor_domain': 'anchor.example',
        'inter_domain': 'inter.example', 'prelander_pool': [], 'status': 'active'})
    assert (await start(flow)).destination_url == routing.FALLBACK_URL


async def test_deleted_legacy_chain_is_not_resurrected_by_cached_document(flow):
    db, redis = flow
    db.redirect_chains.docs.append({'_id': ObjectId(), 'anchor_domain': 'HTTPS://ANCHOR.EXAMPLE/',
        'intermediate_domain': 'inter.example', 'pre_lander_pool': ['two.example'], 'status': 'active'})
    assert await routing.resolve_active_chain(db, None, 'anchor.example', redis)
    db.redirect_chains.docs.clear()
    assert await routing.resolve_active_chain(db, None, 'anchor.example', redis) is None


async def test_domain_edit_invalidates_cached_pool_and_role_but_keeps_clicks(flow, monkeypatch):
    from app.cache import redis_client
    db, redis = flow
    monkeypatch.setattr(redis_client, 'get_redis', lambda: redis)
    monkeypatch.setattr('random.uniform', lambda low, high: 0)
    original = await start(flow)
    assert await domain_role(db, 'one.example', redis) == 'prelander'
    ticket = await redis.get('redirect_hop:' + original.destination_url.rsplit('/', 1)[-1])
    assert ticket is not None
    await domains.update_domain(db, str(db.redirection_domains.docs[2]['_id']), {'status': 'paused'})
    assert await domain_role(db, 'one.example', redis) is None
    assert (await start(flow)).prelander_url == 'https://two.example'
    assert await redis.get('redirect_hop:' + original.destination_url.rsplit('/', 1)[-1]) == ticket


async def test_assignment_then_default_then_unassigned_priority(flow, monkeypatch):
    db, _ = flow
    db.redirection_domains.docs[2]['publisher_ids'] = ['publisher-1']
    db.redirection_domains.docs[3]['is_default'] = True
    monkeypatch.setattr('random.uniform', lambda low, high: high)
    assert (await start(flow, 'publisher-1')).prelander_url == 'https://one.example'
    assert (await start(flow, 'publisher-2')).prelander_url == 'https://two.example'


async def test_chain_missing_inter_cannot_borrow_global_inter(flow):
    db, _ = flow
    db.redirect_chains.docs.append({'_id': ObjectId(), 'anchor_domain': 'anchor.example',
        'prelander_pool': ['two.example'], 'status': 'active'})
    assert (await start(flow)).destination_url == routing.FALLBACK_URL


async def test_chain_lookup_failure_does_not_select_default_domains(flow, monkeypatch):
    db, redis = flow
    monkeypatch.setattr(db.redirect_chains, 'find_one', AsyncMock(side_effect=ConnectionError('unavailable')))
    with pytest.raises(ConnectionError):
        await routing.resolve_active_chain(db, None, 'anchor.example', redis)


async def test_no_campaign_has_a_valid_fallback_response(flow, monkeypatch):
    from app.services import targeting_engine as targeting
    monkeypatch.setattr(targeting, 'resolve_campaign_for_click', AsyncMock(return_value=None))
    assert (await start(flow)).destination_url == routing.FALLBACK_URL


async def test_chain_domain_spellings_and_duplicate_pool_entries(flow, monkeypatch):
    from app.models.redirect_chain import CreateRedirectChainRequest
    db, _ = flow
    request = CreateRedirectChainRequest(name='Normalized', anchor_domain='HTTPS://ANCHOR.EXAMPLE/',
        inter_domain='https://INTER.example/', prelander_pool=['HTTPS://ONE.EXAMPLE/', 'one.example', 'two.example'])
    assert request.anchor_domain == 'anchor.example'
    assert request.inter_domain == 'inter.example'
    # Duplicate representations must not multiply a domain's configured weight.
    monkeypatch.setattr('random.uniform', lambda low, high: high * 0.6)
    assert await domains.select_active_prelander(db, request.prelander_pool) == 'two.example'


async def test_shared_inter_keeps_each_anchors_chain_isolated(flow):
    db, _ = flow
    db.redirection_domains.docs += [domain('second-anchor.example', 'anchor'), domain('extra.example', 'inter')]
    for anchor, pool, extras in [('anchor.example', 'one.example', ['extra.example']),
                                 ('second-anchor.example', 'two.example', [])]:
        db.redirect_chains.docs.append({'_id': ObjectId(), 'anchor_domain': anchor,
            'inter_domain': 'inter.example', 'extra_domains': extras,
            'prelander_pool': [pool], 'status': 'active'})
    first = await start(flow)
    second = await start(flow, host='second-anchor.example')
    for ctx, expected_hosts, final in [(second, ['inter.example'], 'two.example'),
                                      (first, ['inter.example', 'extra.example'], 'one.example')]:
        hosts, url = await follow(flow, ctx)
        assert hosts == expected_hosts
        assert url.startswith(f'https://{final}/_auth/')


@pytest.mark.parametrize('available', [True, False])
async def test_chain_uses_only_its_active_positive_weight_pool(flow, available):
    db, _ = flow
    db.redirect_chains.docs.append({'_id': ObjectId(), 'anchor_domain': 'anchor.example',
        'inter_domain': 'inter.example', 'prelander_pool': ['one.example', 'two.example'], 'status': 'active'})
    db.redirection_domains.docs[2]['status'] = 'paused'
    db.redirection_domains.docs[3]['weight'] = 1 if available else 0
    ctx = await start(flow)
    if available:
        assert ctx.prelander_url == 'https://two.example'
        assert (await follow(flow, ctx))[1].startswith('https://two.example/_auth/')
    else:
        assert ctx.destination_url == routing.FALLBACK_URL


async def test_default_without_inter_goes_to_authorized_prelander(flow):
    db, _ = flow
    db.redirection_domains.docs = [d for d in db.redirection_domains.docs if d['domain_type'] != 'inter']
    ctx = await start(flow)
    assert (await follow(flow, ctx)) == ([], ctx.destination_url)
    assert ctx.destination_url.startswith(ctx.prelander_url + '/_auth/')
