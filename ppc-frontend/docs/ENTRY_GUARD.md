# Conditional Entry Access — Protected Landing Flow

The public landing page (`/`) can be hidden from direct visitors. Only users who
arrive via a link on an **allowed referring domain** receive a short-lived session
cookie and see the normal site UI.

## How it works

```
Request → middleware (server-side)
              │
              ├─ Valid entry_session cookie? → serve app (reload / back / forward OK)
              │
              ├─ Referer hostname in ALLOWED_ENTRY_DOMAINS? → create cookie → serve app
              │
              └─ Otherwise → 302 redirect to ENTRY_FALLBACK_URL
```

Protection runs in **Next.js Edge Middleware** (`middleware.ts`). No client-side
JavaScript is used for authorization.

## Environment variables

Configure in `ppc-frontend/.env.local` (dev) or Docker env / `deployment/.env.production`:

| Variable | Required | Description |
|----------|----------|-------------|
| `ALLOWED_ENTRY_DOMAINS` | Yes (when enabled) | Comma-separated full origin URLs, e.g. `https://browsmac.org,https://www.browsmac.org`. Hostnames are extracted and matched **exactly** (lookalike domains are rejected). |
| `ENTRY_FALLBACK_URL` | Yes (when enabled) | External redirect target for denied requests, e.g. `https://www.google.com/`. **Must not** be your own site hostname (prevents redirect loops). |
| `ENTRY_SESSION_TTL` | No | Session lifetime in seconds. Default `900` (15 minutes). |
| `ENTRY_SESSION_SECRET` | Yes (to enable) | HMAC-SHA256 secret, ≥32 chars. Generate: `openssl rand -hex 32`. If **blank**, the entry guard is **disabled** (useful for local dev). |

## What is protected

| Path | Entry guard | Notes |
|------|-------------|-------|
| `/` | Yes | Main landing page |
| `/admin/*`, `/publisher/*` | No | Existing auth cookies |
| `/d/*`, `/prelander` | No | Prelander slugs on redirect domains |
| `/api/*` | No | Proxied to FastAPI |
| `/_next/*`, static assets | No | Excluded from middleware matcher |

## Cookie details

- Name: `entry_session`
- Format: `<unix_timestamp>.<hmac_sha256_base64url>`
- Flags: `HttpOnly`, `SameSite=Lax`, `Secure` (HTTPS / Cloudflare only)

## Server logs

| Event | Meaning |
|-------|---------|
| `ENTRY_ACCESS_GRANTED` | Valid session cookie |
| `ENTRY_SESSION_CREATED` | New session from allowed referrer |
| `ENTRY_ACCESS_DENIED` | Redirected to fallback |
| `ENTRY_SESSION_EXPIRED` | Cookie TTL exceeded |
| `ENTRY_INVALID_REFERRER` | Referrer present but not on allowlist |

Secrets and raw tokens are never logged.

## Local testing

```bash
# ppc-frontend/.env.local
ALLOWED_ENTRY_DOMAINS=https://browsmac.org
ENTRY_FALLBACK_URL=https://www.google.com/
ENTRY_SESSION_TTL=900
ENTRY_SESSION_SECRET=$(openssl rand -hex 32)
```

```bash
cd ppc-frontend && npm run dev
```

```bash
# Test 1 — direct visit → redirect
curl -I http://localhost:3000/

# Test 2 — allowed referrer → 200 + Set-Cookie
curl -I -H "Referer: https://browsmac.org/page" http://localhost:3000/

# Test 3 — reload with cookie → 200
TOKEN="<from Set-Cookie>"
curl -I -H "Cookie: entry_session=$TOKEN" http://localhost:3000/
```

## Production (Cloudflare → Nginx → Next.js)

1. Set all four variables in `deployment/.env.production` (see example there).
2. Ensure `ENTRY_FALLBACK_URL` points to an **external** host.
3. Redeploy frontend: `bash deployment/5-update.sh` or `docker compose -f docker-compose.prod.yml up -d --build nextjs`.
4. Confirm HTTPS — `Secure` cookies require TLS (Cloudflare origin cert is fine).

## Rollback

Set `ENTRY_SESSION_SECRET=` (empty) and redeploy the frontend container. The
guard is disabled when the secret is blank; `/` behaves as a normal public page.

## Tests

Logic tests (Python mirror of TypeScript helpers):

```bash
cd ppc-backend && pytest tests/test_entry_guard.py -v
```
