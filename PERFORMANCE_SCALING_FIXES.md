# Performance & Scaling Fixes — Production Crash at ~200 rps

Server: 9 vCPU / 18 GB RAM. Symptom: the whole site stopped serving pages at
roughly 180–250 requests/second.

## Root causes found

| # | Cause | Impact |
|---|-------|--------|
| 1 | Duplicate-click check queried `clicks` on `{"fingerprint", "created_at"}` — but clicks are written with `timestamp`, and there was **no `fingerprint` index** | **Full collection scan per click** — the main crash cause |
| 2 | ~20 sequential Mongo round-trips per `/click` (structures, publisher/website ids ×7, domain roles ×3, campaigns ×3, offers to_list(200), chains 200-doc scan, settings, landing pages) | DB saturation → every page's `auth_request` subrequest also stalled → **all pages down** |
| 3 | uvicorn `--timeout-keep-alive 10` vs nginx upstream `keepalive_timeout 60s` — uvicorn closed connections nginx was still holding | Random 502 "upstream prematurely closed" under load |
| 4 | `resolve_campaign_for_click` step 5 loaded **all active campaigns per click** (`to_list(length=None)`) | CPU + RAM blowup on the hottest path |

## Fixes

### 1. Indexes (`app/database.py`)
- `clicks (fingerprint, timestamp DESC)` — turns the duplicate check into an index seek
- `offers (campaign_id, status)`, `offers (status)`, `offers (publisher_ids)`
- `landing_pages (campaign_id, status)`
- `redirect_chains (anchor_domain, status)`
- `geo_rules (country_code, status)`
- `ip_blacklist (ip_address)`, `security_audit_log (created_at DESC)`

> First deploy after this change builds the new indexes — the first startup can take
> longer before `/health` turns green. Subsequent restarts are instant.

### 2. Duplicate-click check fixed (`fraud_detection_service.check_duplicate_click`)
Now matches `timestamp` **or** `created_at` (keeps old test fixtures working) and hits
the new compound index instead of scanning millions of click documents.

### 3. Hot-path Redis cache (`app/cache/kv_cache.py`, TTL 30–120 s)
Fail-open helper: Redis errors fall through to the DB, caching never breaks a request.
Cached lookups:

- Smartlink structures (1 query/click → ~0)
- Publisher / website id resolution (up to 7 queries/click → ~0)
- Domain roles — used by the domain middleware, nginx `auth_request`, hop validation (3+ queries each → 0)
- Campaign resolution steps 1–4 + lean active-campaign snapshot for the weighted pick
- Destination resolution result (offers/geo/device/campaign/fallback + referrer suppression)
- Campaign / offer bypass flags, global fallback URL, stats host
- Redirection chains (removes the 200-doc scan per anchor), landing pages, prelander pools, domain URLs

Admin edits surface within the TTL (≤60 s). Campaign cache invalidation also drops the
snapshot key, so admin campaign changes apply immediately.

### 4. Keepalive race fixed (`docker/entrypoint.sh`)
uvicorn keep-alive raised 10 s → **75 s** (above nginx's 60 s upstream keepalive), so
nginx always closes the connection first — no more reuse-after-close 502s.
Backlog raised 4096 → 8192.

### 5. Capacity settings (`docker-compose.prod.yml`)
- `WEB_CONCURRENCY` 6 → **8** uvicorn workers (9 vCPU; Mongo/Redis/nginx still fit)
- Celery worker concurrency 4 → **6**, memory limit 1.5 G → 2 G
- MongoDB `--maxConns` 1000 → **2000** (8 workers × pool 40 + 6 celery × 40 no longer near the ceiling)

## Resulting hot path (per `/click`)

Before: ~20 Mongo queries + 2 writes, several full scans.
After: **1 insert + 1 update** (Mongo) + ~15 in-memory Redis ops (all O(1)),
with per-worker inflight cap (`API_MAX_INFLIGHT=256`) and nginx keepalive pools unchanged.

## Verify after deploy

```bash
# 1. Health
curl -k https://localhost/health

# 2. Load test the click path (redirects recorded, not followed)
node deployment/load-test.cjs --url https://localhost/click?pub=YOUR_PUB \
  --requests 20000 --concurrency 500 --max-error-rate 0.01 --max-p95-ms 500

# 3. Load test a portal page (auth subrequest path)
node deployment/load-test.cjs --url https://localhost/ \
  --requests 10000 --concurrency 250 --max-error-rate 0.01 --max-p95-ms 1000

# 4. Watch containers while testing
docker stats
```

Gate for "handles thousands of rps": ≥1000 rps sustained, error rate ≤1 %, p95 ≤500 ms,
no container OOM-restarts (`docker inspect --format '{{.State.OOMKilled}}' ppc_fastapi`).

Tests: hot-path caching is disabled under pytest (`tests/conftest.py` sets
`CLICK_HOT_CACHE=false`), so the whole existing suite validates unchanged DB semantics.