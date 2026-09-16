# Prelander Authorization — Manual QA Guide (STEP 20)

Reproducible browser verification of the security architecture
(STEPS 1–19 implemented; this document is the human half of acceptance).

## Preconditions

- Deployment running the current `main` (nginx + frontend + backend + Redis + MongoDB).
- A publisher with an **active** Smartlink `{anchor-domain}/click?pub=PUB123&site=…`
  routed to a **prelander** (Bypass OFF, Inter + Prelander domains configured).
- Browser A: Chrome (or any). Browser B: a *different* browser (e.g. Firefox).
- `PRELANDER_AUTH_REQUIRED=true` (default) and default TTLs
  (`PRELANDER_SESSION_TTL=300`, `PRELANDER_HANDOFF_TTL=60`).

## Acceptance Test A — full legitimate flow

1. In Browser A, open the Smartlink: `https://anchor-domain.com/click?pub=PUB123…`
2. **Expect:**
   - Anchor responds (redirects; may flash a blank/please-wait page).
   - Lands on the **Inter** domain `/d/{slug}` with the 0.75s loader.
   - Loader transitions to the **Prelander** domain `https://prelander-domain.com/d/{slug}`.
   - The prelander **renders the protected content** (file info, campaign link, password).
   - The visible URL is **clean**: only `/d/{slug}` — no `?campaign=`, no `?token=`, no internal ids.
3. Network tab: after the hop you should see `GET /api/prelander/handoff` (mint)
   then `GET /_auth/{token}` (exchange) then `GET /d/{slug}` — the token appears
   once and never repeats.

## Acceptance Test B — copied URL, fresh session (no cookies)

1. Complete Test A. Copy the final visible URL `https://prelander-domain.com/d/{slug}`.
2. In the **same browser**, open a new private/incognito window. Paste the URL. Enter.
3. **Expect:** the neutral *"This link is no longer available."* page (or the
   configured `PRELANDER_DENIED_MODE`). **No** protected content.
   - *Note (documented edge):* incognito on the **same machine with the exact
     same browser build** shares IP + User-Agent, so the server may treat it as
     the original browser and ALLOW it. This is browser architecture (see
     `docs/PRELANDER_AUTHORIZATION.md` § incognito). To test strictly, use a
     different machine, a VPN, or Browser B (next test).

## Acceptance Test C — another browser

1. Paste the same URL into **Browser B** (different UA) — same machine is fine.
2. **Expect:** denied. A different browser never passes the User-Agent binding.

## Acceptance Test D — expiration

1. Complete Test A, keep the prelander open.
2. Wait until the authorization expires (default **5 minutes** after the click
   — configured via `PRELANDER_SESSION_TTL`).
3. Refresh the prelander.
4. **Expect:** denied fallback (the browsing session cookie died with its
   authorization; a fresh `/d/{slug}` load gets nothing).

## Acceptance Test E — valid refresh (no extra click)

1. Complete Test A. **Note the click count** in admin Statistics for this
   publisher/site (or the click total before the test).
2. Refresh the prelander page 5 times within the TTL.
3. **Expect:**
   - Page keeps working — same content, no re-authentication hop.
   - **Click count unchanged**: refreshes ride the browsing session
     (`mpa_pls` cookie), never a new `/click`.
4. Back/forward buttons: same behavior — the page works, no new clicks.

## Acceptance Test F — two campaigns, same prelander hostname

1. Set up two campaigns (A and B) both routed to the SAME prelander domain.
2. Produce two Smartlink clicks (two machines, or machine + VPN) — one per campaign.
3. **Expect:** each visitor's prelander shows **its own campaign's** content —
   campaign A's visitor sees A's offer/password, B's sees B's. No cross-session
   leakage even though the hostname is identical for both.

## Additional verifications (STEP 13–16)

- **Headers:** on the prelander page (devtools → Network → the document
  response) check: `Content-Security-Policy` present (with `frame-ancestors
  'none'`, `object-src 'none'`), `X-Frame-Options: DENY`, `X-Content-Type-Options:
  nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy` present. Same on portal pages (stricter CSP).
- **Cookies:** devtools → Application → Cookies:
  - `mpa_pls` on the prelander domain: **HttpOnly** ✓ (no JS access), Secure ✓,
    SameSite=Lax ✓.
  - `mpa_pla` on the anchor domain: HttpOnly ✓ Secure ✓ SameSite=Lax ✓.
- **Assets:** CSS/JS/images of the prelander still load (CSP allows https:
  resources on `/d/` pages).
- **Replay (back button):** after the prelander loads, press Back to the
  `/prelander/_auth/{token}` response and Forward again — the token was
  consumed; expect the denied fallback on the back-hit.
- **Rate limit:** hammer `/_auth/{random}` 30+ times in a minute from one IP →
  `429 Too many requests` (defense-in-depth; tokens are 256-bit random so
  guessing is infeasible regardless).
- **Logs:** backend logs show structured events (`event=redirect_session_created`,
  `event=handoff_token_exchanged`, `event=prelander_access_allowed`, …) and
  **never** a raw handoff token in request logs (`/prelander/_auth/{token}`
  redacted).

## Environment configuration (STEP 21)

| Variable | Default | Meaning |
|---|---|---|
| `PRELANDER_SESSION_TTL` | `300` | authorization lifetime (s) |
| `PRELANDER_HANDOFF_TTL` | `60` | one-time handoff validity (s) |
| `PRELANDER_AUTH_REQUIRED` | `true` | emergency kill switch |
| `PRELANDER_IP_MODE` | `relaxed` | `strict` \| `relaxed` |
| `PRELANDER_COOKIE_SECURE` | `true` | Secure cookie flag |
| `PRELANDER_COOKIE_SAMESITE` | `lax` | `lax` \| `strict` \| `none` |
| `PRELANDER_AUTH_RATE_LIMIT` | `30` | per-IP auth-surface requests |
| `PRELANDER_AUTH_RATE_WINDOW` | `60` | rate-limit window (s) |
| `PRELANDER_DENIED_MODE` | `generic_page` | `generic_page` \| `not_found` \| `forbidden` \| `redirect` |
| `PRELANDER_DENIED_FALLBACK_URL` | — | target for `redirect` mode |