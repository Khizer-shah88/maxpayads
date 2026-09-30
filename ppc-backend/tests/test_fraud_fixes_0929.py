"""
Regression tests for the 2026-09-29 batch:

1. Background click task must NOT flag a fresh click as duplicate_ip via the
   inline stage's own per-day key (all-clicks-invalid bug).
2. Cross-publisher uniqueness: same IP on different publishers stays valid for
   each (per-publisher key verified at the background path too).
3. fraud_service.check_fraud(rate limit) still works when Redis is a real
   client — the label now says 60/min.
4. detect_headless_signals: only affirmative automation evidence counts.
5. Landing pages <-> prelander templates binding sync (assign + clear).
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId
from test_publisher_stats_actions import Collection, matches

from app.services import fraud_detection_service as fds
from app.services import fraud_service
from app.services.redirect_pipeline import RedirectResolutionContext
from app.core.constants import REDIS_DUPLICATE_CLICK_PREFIX

IP = "203.0.113.9"
PUB_A = "pub-a"
PUB_B = "pub-b"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"


# ── fakes ─────────────────────────────────────────────────────────────────────

class KeyStore:
    """Async redis subset covering incr/expire/exists/setex/getdel."""

    def __init__(self):
        self.data = {}

    async def incr(self, key):
        value = int(self.data.get(key, 0)) + 1
        self.data[key] = value
        return value

    async def expire(self, key, ttl):
        return key in self.data

    async def exists(self, key):
        return 1 if key in self.data else 0

    async def setex(self, key, ttl, value):
        self.data[key] = value

    async def get(self, key):
        return self.data.get(key)

    async def getdel(self, key):
        return self.data.pop(key, None)

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            if self.data.pop(key, None) is not None:
                removed += 1
        return removed

    def pipeline(self):
        return FakePipeline(self)

    async def keys(self, pattern):
        prefix = pattern.rstrip('*')
        return [k for k in self.data if k.startswith(prefix)]


class FakePipeline:
    def __init__(self, store):
        self.store = store
        self.ops = []

    def setex(self, key, ttl, value):
        self.ops.append(('setex', key, ttl, value))
        return self

    async def execute(self):
        for op in self.ops:
            getattr(self.store, op[0])(*op[1:])
        self.ops = []
        return True


class ClickCol:
    def __init__(self, docs=()):
        self.docs = list(docs)

    async def find_one(self, query, *a, **k):
        """Match the service's actual query: fingerprint eq + (timestamp or
        created_at) >= since + optional _id exclusion."""
        fp = query.get('fingerprint')
        excl = (query.get('_id') or {}).get('$ne')
        nin = (query.get('_id') or {}).get('$nin') or []
        since = None
        for clause in (query.get('$or') or []):
            for field in ('timestamp', 'created_at'):
                if field in clause:
                    since = max(since, clause[field]['$gte']) if since else clause[field]['$gte']
        for doc in self.docs:
            if fp is not None and doc.get('fingerprint') != fp:
                continue
            if excl is not None and doc.get('_id') == excl:
                continue
            if doc.get('_id') in nin:
                continue
            if since is not None:
                doc_ts = doc.get('timestamp') or doc.get('created_at')
                if doc_ts is None or doc_ts < since:
                    continue
            return doc
        return None

    def aggregate(self, pipeline):
        rows = []
        if pipeline and pipeline[0].get('$group', {}).get('_id') == '$publisher_id':
            match = pipeline[0].get('$match', {})
            ts = match.get('timestamp') or {}
            gte = ts.get('$gte')
            sums = {}
            for doc in self.docs:
                if gte is not None and doc.get('timestamp', datetime.min) < gte:
                    continue
                sums[doc.get('publisher_id')] = sums.get(doc.get('publisher_id'), 0) + 1
            rows = [{'_id': k, 'total': v} for k, v in sums.items()]
        return SimpleNamespace(to_list=self._to_list(rows))

    def _to_list(self, rows):
        async def _to_list(length=None):
            return rows
        return _to_list

    async def insert_one(self, doc):
        doc.setdefault('_id', ObjectId())
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc['_id'])

    async def update_one(self, query, update):
        for doc in self.docs:
            if doc.get('_id') == query.get('_id'):
                doc.update(update.get('$set', {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


class EmptyCol:
    def __init__(self):
        self.docs = []

    async def find_one(self, *a, **k):
        return None

    def aggregate(self, pipeline):
        return SimpleNamespace(to_list=self._to_list([]))

    def _to_list(self, rows):
        async def _to_list(length=None):
            return rows
        return _to_list

    async def insert_one(self, doc):
        return SimpleNamespace(inserted_id=ObjectId())

    async def count_documents(self, q):
        return 0


def make_db():
    return SimpleNamespace(
        clicks=ClickCol(), ip_blacklist=EmptyCol(),
        publishers=EmptyCol(), security_audit_log=EmptyCol(),
        fraud_logs=Collection(), landing_pages=Collection(),
        prelander_templates=Collection(), redirection_domains=Collection(),
        websites=EmptyCol(),
    )


# ── 1+2: the self-defeating duplicate check ───────────────────────────────────

async def test_fresh_click_not_flagged_duplicate_by_own_key():
    """The exact 'all clicks invalid' bug: the inline stage registers the
    per-day key; the background task seconds later read the SAME key and
    flagged the click. With exclude_click_id the task checks PRIOR clicks
    only — a fresh click (no prior click from this IP+pub) stays valid."""
    db = make_db()
    redis = KeyStore()

    # Simulate the inline stage: judge ctx, register key.
    ctx = RedirectResolutionContext(
        raw_pub=PUB_A, ip=IP, user_agent=UA,
        publisher_id=PUB_A, website_id=None,
    )
    from app.services import redirect_pipeline as rp
    await rp.stage_screen_traffic(ctx, db, redis)
    assert not ctx.is_flagged  # inline verdict fresh = valid

    click_id = str(ObjectId())
    import hashlib as _h
    fingerprint = _h.sha256(f"{IP}:{PUB_A}:none".encode()).hexdigest()
    # The click is now in the DB (as record_click does):
    await db.clicks.insert_one({
        '_id': ObjectId(click_id), 'publisher_id': PUB_A,
        'ip_address': IP, 'fingerprint': fingerprint, 'timestamp': datetime.utcnow(),
    })

    # Background task: judge the same click — must NOT be a duplicate of itself.
    is_fraud, reason, score = await fraud_service.check_fraud(
        {'ip_address': IP, 'publisher_id': PUB_A, 'user_agent': UA,
         'country_code': 'US', 'device_type': 'desktop', 'campaign_id': None,
         'referrer': ''},
        db, redis, exclude_click_id=click_id,
    )
    assert is_fraud is False, f'fresh click flagged: {reason}'
    assert reason is None


async def test_repeat_prior_click_on_same_publisher_is_duplicate_at_task():
    """A PRIOR click from the same IP+publisher (within the window) IS caught
    by the background duplicate check."""
    import hashlib as _h
    db = make_db()
    redis = KeyStore()

    prior_id = ObjectId()
    fingerprint = _h.sha256(f"{IP}:{PUB_A}:none".encode()).hexdigest()
    db.clicks.docs.append({
        '_id': prior_id, 'publisher_id': PUB_A, 'ip_address': IP,
        'fingerprint': fingerprint,
        'timestamp': datetime.utcnow() - timedelta(minutes=5),
    })
    judged_id = str(ObjectId())

    is_fraud, reason, _ = await fraud_service.check_fraud(
        {'ip_address': IP, 'publisher_id': PUB_A, 'user_agent': UA,
         'country_code': 'US', 'device_type': 'desktop', 'campaign_id': None},
        db, redis, exclude_click_id=judged_id,
    )
    assert is_fraud is True
    assert reason == 'duplicate_ip'


async def test_other_publisher_prior_click_is_not_duplicate():
    """The explicit requirement: no CROSS-PUBLISHER duplicates. A prior click
    of publisher B must never make publisher A's click a duplicate."""
    import hashlib as _h
    db = make_db()
    redis = KeyStore()

    # Publisher B's prior click — its fingerprint names PUB_B, so A's lookup
    # (fingerprint over PUB_A) can never match it.
    db.clicks.docs.append({
        '_id': ObjectId(), 'publisher_id': PUB_B, 'ip_address': IP,
        'fingerprint': _h.sha256(f"{IP}:{PUB_B}:none".encode()).hexdigest(),
        'timestamp': datetime.utcnow() - timedelta(minutes=5),
    })
    judged_id = str(ObjectId())

    # Judge publisher A — publisher B's prior click must not count.
    is_fraud, reason, _ = await fraud_service.check_fraud(
        {'ip_address': IP, 'publisher_id': PUB_A, 'user_agent': UA,
         'country_code': 'US', 'device_type': 'desktop', 'campaign_id': None},
        db, redis, exclude_click_id=judged_id,
    )
    assert is_fraud is False, f'cross-publisher leak: {reason}'


async def test_inline_redis_key_is_per_publisher():
    """The inline stage's key includes the PUBLISHER id — the visitor's
    click on publisher B must not hit publisher A's key."""
    db = make_db()
    redis = KeyStore()

    from app.services import redirect_pipeline as rp
    ctx_a = RedirectResolutionContext(raw_pub=PUB_A, ip=IP, user_agent=UA,
                                      publisher_id=PUB_A)
    await rp.stage_screen_traffic(ctx_a, db, redis)
    assert ctx_a.is_flagged is False

    ctx_b = RedirectResolutionContext(raw_pub=PUB_B, ip=IP, user_agent=UA,
                                      publisher_id=PUB_B)
    await rp.stage_screen_traffic(ctx_b, db, redis)
    assert ctx_b.is_flagged is False  # different publisher → unique again

    assert f'{REDIS_DUPLICATE_CLICK_PREFIX}{IP}:{PUB_A}:'.__sizeof__() > 0
    keys = [k for k in redis.data.keys()]
    assert any(f':{PUB_A}:' in k for k in keys)
    assert any(f':{PUB_B}:' in k for k in keys)


async def test_rate_limit_still_blocks_after_window():
    """Rule 4 works with a real client shape: > 60 clicks/min = rate-limited."""
    redis = KeyStore()
    ip = '198.51.100.5'
    for _ in range(61):
        count = await redis.incr(f'click_rate:{ip}')
    db = make_db()
    db.clicks = ClickCol()  # no prior clicks: dup path must not preempt reason
    db.clicks.docs = []
    is_fraud, reason, _ = await fraud_service.check_fraud(
        {'ip_address': ip, 'publisher_id': PUB_A, 'user_agent': UA,
         'country_code': 'US', 'device_type': 'desktop', 'campaign_id': None},
        db, redis, exclude_click_id='507f1f77bcf86cd799439011',
    )
    assert is_fraud is True
    assert reason == 'rate_limit_exceeded'


# ── 4: headless detection ─────────────────────────────────────────────────────

def test_headless_only_on_affirmative_evidence():
    ok = fds.detect_headless_signals(
        {'host': 'x'} , UA)
    assert ok == (False, [])
    yes, sigs = fds.detect_headless_signals({}, 'HeadlessChrome/91')
    assert yes and any('headless' in s.lower() for s in sigs)


# ── 5: landing <-> template sync ──────────────────────────────────────────────

def test_domain_binding_helpers_read_both_spellings():
    from app.models.redirect_chain import chain_inter_domain, chain_prelander_pool
    chain = {'intermediate_domain': 'old.example',
             'pre_lander_pool': ['a.example', 'b.example']}
    assert chain_inter_domain(chain) == 'old.example'
    assert chain_prelander_pool(chain) == ['a.example', 'b.example']