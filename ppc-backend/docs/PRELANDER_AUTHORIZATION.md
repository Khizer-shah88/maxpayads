# Prelander Authorization — Behavior Documentation

Server-side authorization for campaign prelander access.
**Core principle: DOMAIN ≠ AUTHORIZATION** — knowing the prelander domain or
URL is never sufficient to see protected content.

## Architecture summary

```
Smartlink /click (Anchor domain)
  → redirect pipeline: identify → screen → record click → route
  → stage_authorize_prelander  — Redis session born (STEP 2/3):
        high-entropy token, full internal context (publisher, site, campaign,
        offer, prelander host, chain, OS/device, country, referrer, click),
        created_at/expires_at, status, consumed_count — TTL from
        PRELANDER_SESSION_TTL (default 300s)
  → Inter /d/{slug}             — 0.75s dwell, hop decision
  → GET /prelander/handoff      — one-time opaque token minted (STEP 4)
  → Prelander /_auth/{handoff}  — ATOMIC consume (GETDEL), browsing session
                                  minted, HttpOnly SameSite=Lax cookie set,
                                  302 → clean /d/{slug} (token gone from URL)
  → GET /prelander/resolve/{slug} — STEP 5 access middleware validates all
                                  11 checks BEFORE any protected data
  → prelander rendered from the validated session's context (STEP 10)
```

## Access matrix (STEP 8)

| Case | Scenario | Result | Why |
|---|---|---|---|
| A | Full Smartlink → Anchor → Inter → Prelander | **ALLOW** | click-time session matches the browser fingerprint + slug |
| B | Prelander URL pasted into a **different browser** | **DENY** | User-Agent is the binding; a different browser never matches any validation path |
| C | Pasted into **incognito/private** window | **DENY**\* | no cookie; session lookup finds nothing for that browser |
| D | Opened **after expiration** | **DENY** | `expires_at` enforced (`PRELANDER_SESSION_TTL`) |
| E | Copied URL, **no authorization/session** anywhere | **DENY** | bare slug has no session to validate |
| F | **Refresh** during an active session | **ALLOW** | browsing-session cookie, no handoff re-use, no new click |

\* **Honest limit (documented, not hidden):** incognito on the *same machine*
with the *same browser build* shares the IP **and** the User-Agent. With no
cookie, the server-side fingerprint index still matches it — the architecture
**cannot** distinguish it from the original profile. Compensating controls:
the slug is route-bound (an authorization for one slug cannot read another),
sessions live only minutes, and the click's fraud screening already ran.

## Duplicate tab — documented behavior

Cookies belong to the **browser profile, not the tab**. A duplicated tab
therefore inherits the same cookie jar AND the same (IP, UA) fingerprint, so
**Tab B is allowed exactly like Tab A**. This is browser architecture, not a
configurable oversight. We do **not** implement tab isolation: it would
require a per-tab nonce plus server validation (a separate requirement, only
worth building if there is a concrete fraud case, and it breaks refresh and
asset loading in subtle ways).

## Same hostname, different campaigns (STEP 10)

Campaign content is determined from the **validated server-side session**,
never from the hostname. Two visitors on `prelander-domain.com` with
campaigns 101 and 202 each receive **their own** campaign's selected content —
the resolve step reads `campaign_id`/`offer_id` off the authorized session.
The visible URL stays clean: `/d/{opaque-slug}` — no `/campaign/123`,
no `?campaign=…&publisher=…` parameters.

## Multiple prelander domains (STEP 9)

Any number of prelander domains are supported. Each domain may carry its own
HTML/template/UI (per-domain template assignment via the admin), and each
authorization records the **selected prelander host** at click time
(`ctx.prelander_url` — the exact domain the router chose). The access
middleware verifies the request's host matches the session's recorded
prelander host, so an authorization for `prelander-a.com` cannot serve
`prelander-b.com` content.

## Replay protection (STEP 11)

State machine: `issued → exchanged → (session) active → completed/expired/revoked`.

- Handoff tokens are consumed **atomically** with Redis `GETDEL` — the
  get-then-delete race window does not exist. Exactly one caller wins;
  every replay (back button, double-click, shared link) finds nothing.
- After the exchange, refreshes/back/forward ride the **browsing session**
  (`mpa_pls` cookie → `prelander_plsess:{id}`), never the handoff.
- Sessions enforce their own lifecycle: consumption ceiling
  (`MAX_CONSUMPTIONS`) flips status to `consumed`; revoke deletes instantly
  (kills the browsing session too); TTL expiry kills all records together.

## IP address policy (STEP 12)

IP is an **anti-abuse signal, never the sole identifier** (carrier NAT,
proxies, corporate networks, VPNs, mid-session mobile rotation). The primary
browser binding is the User-Agent; IP checking is **configurable and
risk-based** via `PRELANDER_IP_MODE`:

- `relaxed` (default) — UA-bound; a rotated IP falls back to the slug-index
  path, which still demands the exact UA and the exact slug. Mobile/VPN safe.
- `strict` — the full (IP+UA) fingerprint must match; rotated IPs are denied.

A different browser on the same IP is denied in **both** modes.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `PRELANDER_SESSION_TTL` | `300` | authorization session lifetime (s) |
| `PRELANDER_HANDOFF_TTL` | `60` | one-time handoff validity (s) |
| `PRELANDER_IP_MODE` | `relaxed` | `strict` \| `relaxed` |
| `PRELANDER_DENIED_MODE` | `generic_page` | `generic_page` \| `not_found` \| `forbidden` \| `redirect` |
| `PRELANDER_DENIED_FALLBACK_URL` | — | safe target for `redirect` mode |
| `PRELANDER_AUTH_REQUIRED` | `true` | emergency kill switch (set `false` to disable the gate) |

Denied access returns the configured fallback — a neutral page that leaks no
campaign ids, publisher ids, offer info, database ids, internal routing,
secrets, or errors.