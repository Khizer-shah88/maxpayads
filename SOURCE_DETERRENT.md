# Source-View Deterrent

> **Source of truth:** `~/view-source-demo/source-deterrent/` (commit 77d5277) —
> `sw.js` and `snippet.html`. Naming, constants, structure and wording here
> follow that reference. Two deltas are applied for this codebase, both marked
> in the worker and justified under "Deltas from the reference" below.
>
> Do **not** copy `~/view-source-demo/public/sw.js`. Its own header calls it
> "BUG 4 — the service worker that hijacks view-source: tabs"; it is a bug
> exhibit with **no loop guard at all**, and it is the worker that was
> reload-looping `localhost:3000` on this machine.
>
> `~/view-source-demo/FINDINGS.md` documents a *different* problem — view-source
> tabs hijacked by accidental server-side redirects (catch-all middleware
> matchers). Worth reading; it is not the spec for this feature.

## Deltas from the reference

**1. Marker gate (`x-sd: 1`).** The reference sweeps every window client, which
is safe in a demo where every page carries the snippet. This app has pages that
*cannot* heartbeat — above all the session-unavailable 403 page, which ships no
script and a `default-src 'none'` CSP, and is served at `/` on prelander
domains. Sweeping it navigated it, it returned silent, and it was navigated
again. That was the outage. A sweep is now scheduled only for navigations whose
response carried the marker.

**2. Durable budget.** The reference keeps the counter in memory and says:
*"If the worker gets killed between loops the cap resets — persist it to the
Cache API if you ever observe that."* Observed: terminating the worker mid-loop
(which the browser does to any idle worker) reset the count and the loop
resumed. It is now persisted in the Cache API and reset on every heartbeat, so
the cap means "3 consecutive navigations that produced no heartbeat".


**Status: STOOD DOWN.** The worker shipped as a tombstone that unregisters
itself. `ENABLE_SOURCE_DETERRENT` defaults to `false`. Do not turn it on until
the checklist at the bottom passes in a real browser.

---

## What this feature is

When someone hits Cmd+U / Ctrl+U, the tab ends up on the normally-rendered page
instead of showing HTML as text.

## What it is not

It does **not** and **cannot** prevent access to the source:

- `curl` and every other HTTP client see the full HTML, unaffected
- DevTools → Network → Response shows everything
- DevTools Elements shows everything
- "Save page as" shows everything
- The very first visit, before the worker installs, shows everything

The HTML is already on the client. This deters a casual Cmd+U and nothing more.
**It is not a security control.** Never cite it as one in a review, a threat
model, or a customer conversation. If something sensitive is reachable in the
client bundle, that needs a server-side fix; this feature does not mitigate it.

It also does not detect view-source specifically. It detects *"this document did
not run JavaScript"* — which is equally true of a visitor with JS disabled, a
hydration crash, a blocked inline script, or an extension. Every safeguard in
the implementation exists to make that misfire harmless.

---

## Why it is stood down

The version that shipped reload-looped real visitors.

The worker navigated **any** window client that had not sent a heartbeat within
the grace period. But the heartbeat only ever shipped on two pages:
`/d/[slug]` and the clean prelander shell. Every other document on the origin
was silent by construction — above all the session-unavailable 403 page
(`lib/prelander-session.ts`), which carries no script *and* a
`default-src 'none'` CSP, so it cannot run one even in principle.

The loop:

1. Visitor's prelander session is absent or expired
2. Middleware serves the 403 page at `/`
3. Worker's `fetch` handler fires → sweep scheduled
4. 1200ms later the client has not pinged → `client.navigate(client.url)`
5. Back to `/` → still no session → 403 again → **goto 3**

`MAX_NAVIGATIONS = 3` did not hold it. The counter was a module-level variable,
and the browser terminates an idle service worker between sweeps. Every restart
reset it to 0, so the pattern was: three reloads, worker idles out, three more,
indefinitely.

Same trap applied to `/d/test`, Next's 404 page, and the empty
`PORTAL_HOST_BLOCKED` 404.

### The second problem

`/source-deterrent-sw.js` returned **404 on every prelander domain**. The
middleware's `isInfraPath` allowlist covered `mp4|webm|png|jpg|jpeg|gif|ico|svg|txt|xml|webmanifest`
but not `.js`, and nginx's prelander blocks had the same gap, so the request
fell through to a 404.

That is worse than it sounds. A 404 on a worker script removes the browser's
only channel for fetching an **update**, so every already-installed worker kept
running its old looping code with no way to receive a fix. Making the path
reachable was the prerequisite for standing the feature down at all.

---

## What changed

| Change | File |
|---|---|
| Worker replaced with a self-unregistering tombstone (no `fetch` handler ⇒ cannot loop) | `ppc-frontend/public/source-deterrent-sw.js` |
| Worker scripts allowed through the portal-hostname gate | `ppc-frontend/middleware.ts` |
| Worker scripts routed on all four non-portal server blocks, `no-store` | `nginx.prod.conf` |
| Kill switch made a **runtime** flag (was baked at build time by next.config `env`) | `ppc-frontend/next.config.js` |
| Kill switch defaults to **off** when unset, in both consumers | `app/clean-shell/route.ts`, `app/d/[slug]/layout.tsx` |
| Kill switch wired into deployment, set to `false` | `docker-compose.prod.yml` |
| Unregister helper scoped to our worker only (it used to unregister *every* worker on the origin) | `ppc-frontend/public/unregister-source-deterrent.js` |
| Repaired implementation, deliberately not served | `ppc-frontend/source-deterrent-sw.repaired.js` |

## Clearing a stuck client

The tombstone handles this automatically: any client that can fetch an update
unregisters itself on activate. For a client whose update check has not fired,
or to clear your own browser:

```js
navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => r.unregister()))
```

`/unregister-source-deterrent.js` does the same thing, scoped to our worker.

### Stale workers on localhost

A service worker registration is scoped to an **origin**, not a project. Every
project you run on `http://localhost:3000` shares one registration store, so a
worker registered by a *different* project keeps controlling this app — and if
its script path does not exist here, you get a silent reload loop plus a
repeating 404 for a file this repo has never contained:

```
GET /sw.js 404
GET / 200
GET /sw.js 404      ← a worker from another project, still in control
```

The page cannot defend against this; the worker intercepts before any page code
runs. Clear it in DevTools → Application → Service Workers → Unregister, or:

```js
navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => r.unregister()))
```

then hard-reload. This is also why both inline scripts skip localhost entirely:
a deterrent worker on a shared dev origin would leak into every other project
you run on that port.

---

## Re-enabling: checklist

Every box must be ticked. The first three are the ones the original rollout
skipped.

- [ ] **Wire the marker header.** The repaired worker only sweeps a navigation
      whose response carries `x-sd: 1`. Nothing emits it yet. Add it to the
      clean-shell `GET` response and to the `/d/[slug]` response — and **only**
      to documents that actually contain the inline heartbeat. This header is
      the entire loop fix; getting it wrong reintroduces the bug.
- [ ] **Deal with `/d/test`.** It is debug scaffolding that renders
      "Test Page Working!" on every prelander domain and does **not** carry the
      heartbeat (it uses the root layout, not `app/d/[slug]/layout.tsx`). If a
      `/d/:path*` header rule gives it the marker, it becomes a loop path.
      Delete it, or exclude it explicitly.
- [ ] **Measure the grace period.** `GRACE_MS = 1200` is a placeholder inherited
      from the original code, which cited no measurement. Measure p95
      navigation → first heartbeat on the slowest device and network this
      project supports, add headroom, and record the number and its basis here.
- [ ] **Measure navigation latency**, before vs after. `respondWith` puts the
      worker in front of every navigation. Confirm it does not disturb Next.js
      data, prefetch or streaming requests.
- [ ] **Unify the two inline scripts.** `clean-shell/route.ts` and
      `d/[slug]/layout.tsx` implement the heartbeat differently — the latter
      posts to `registration.active/waiting/installing` instead of
      `navigator.serviceWorker.controller` and `console.log`s on every 400ms
      tick, which will flood production consoles. One implementation, one place.
- [ ] Confirm CSP on both pages allows `'unsafe-inline'` under `script-src` and
      `'self'` under `worker-src`. Both do today.
- [ ] Copy `source-deterrent-sw.repaired.js` → `public/source-deterrent-sw.js`.
- [ ] Set `ENABLE_SOURCE_DETERRENT=true` and `docker compose up -d nextjs`.

## Acceptance tests

Run in a real browser against a real prelander domain. Record what actually
happened, not what should happen.

| # | Test | Expected |
|---|---|---|
| 1 | view-source on a profile with the worker installed | lands on rendered page |
| 2 | view-source on a **fresh** profile | shows source — expected and unavoidable, confirm rather than fix |
| 3 | JS disabled | page readable, **no reload loop**; count document requests and show they stop at the cap |
| 4 | `curl -s <url>` | full HTML, unaffected |
| 5 | Navigation latency, before vs after | no meaningful regression |
| 6 | Kill switch `false` | feature fully inert; unregister snippet removes an installed worker |
| 7 | **Session-expired 403 page** — the page that caused the outage | renders once, stays put, zero navigations |

Test 7 is not optional. It is the regression test for this incident.

## Browser support

Verified in Chrome only, by the original author. Whether Firefox and Safari let
a service worker observe a view-source navigation, and whether their
`client.navigate()` behaves the same, is **untested**. `event.resultingClientId`
availability on view-source navigations is likewise unverified — the repaired
worker falls back to a full (marker-gated) sweep when it is empty. Where the
approach does not work the correct outcome is "feature absent", never a broken
page.
