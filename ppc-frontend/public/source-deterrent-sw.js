// Source-view deterrent -- service worker half.
//
// SOURCE OF TRUTH: ~/view-source-demo/source-deterrent/sw.js (commit 77d5277).
// Naming, constants and structure follow that reference. Two deltas are applied
// for this codebase, both documented at their site below:
//   1. MARKER GATE      -- required here, see "WHY THE MARKER" below
//   2. DURABLE BUDGET   -- the reference's own documented upgrade path
// Do NOT copy ~/view-source-demo/public/sw.js: that file is the "BUG 4" exhibit
// and has no loop guard whatsoever.
//
// HOW IT WORKS
// A view-source: tab cannot execute JavaScript, so it never sends the heartbeat
// that the page snippet sends. Nothing in the API exposes the "view-source:"
// prefix -- request.url and client.url both read as the plain URL -- so the tab
// is identified by absence. Any window client still silent after GRACE_MS is
// navigated to its own url, which re-opens it as an ordinary document.
//
// WHAT THIS CANNOT DO -- read before shipping
// curl and every other HTTP client, DevTools -> Network -> Response, DevTools
// Elements, "Save page as", the first visit before this worker installs, and any
// browser with JS disabled all still see everything. The HTML is already on the
// client by the time this runs. This deters a casual Cmd/Ctrl+U. It is NOT a
// security control. Secrets still belong server-side.
//
// It does not detect view-source specifically. It detects "this document did not
// run JavaScript", which is equally true of JS disabled, a hydration crash, a
// blocked inline script or an extension. The guards below exist to make that
// misfire harmless.
//
// VERIFIED IN CHROME ONLY. Whether Firefox and Safari let a service worker see a
// view-source: navigation, and whether their client.navigate() behaves the same,
// is untested. Treat every other browser as "feature absent" until tested.

const PING = "SOURCE_DETERRENT_PING";

// Tune from real data: p95 time from navigation to first heartbeat on the
// slowest device and network you support, plus headroom. Too low and you bounce
// real users whose JS is merely slow; too high and the source is readable for
// that long. Lowered to 50 ms -- as small as practical while still giving the
// page's inline script a chance to post its heartbeat on a fast connection.
// NOT yet measured against maxpayads traffic -- see SOURCE_DETERRENT.md.
const GRACE_MS = 50;

// Loop guard -- the most important line here. Without a cap, a visitor who
// genuinely cannot run JS (JS disabled, hydration crash, blocked inline script,
// extension interference) gets navigated on every sweep, forever. A client that
// cannot be "fixed" must be left alone on a readable page.
const MAX_NAVIGATIONS = 3;

// ── DELTA 1: MARKER GATE ────────────────────────────────────────────────────
// WHY THE MARKER: the reference sweeps every window client, which is safe in a
// demo where every page carries the snippet. This app has pages that CANNOT
// heartbeat -- above all the session-unavailable 403 page, which ships no script
// and a `default-src 'none'` CSP, served at `/` on prelander domains. Sweeping
// it navigated it, it came back silent, and it was navigated again: a live
// reload loop for real visitors. A sweep is now scheduled ONLY for a navigation
// whose response carried `x-sd: 1`, which only instrumented documents emit.
const MARKER = "x-sd";

// ── DELTA 2: DURABLE BUDGET ─────────────────────────────────────────────────
// The reference keeps the counter in memory and notes: "If the worker gets
// killed between loops the cap resets -- persist it to the Cache API if you ever
// observe that." Observed: terminating the worker mid-loop (which the browser
// does to any idle worker) reset the count and the loop resumed. So it is
// persisted here, and reset to 0 on every heartbeat -- making the cap mean
// "3 consecutive navigations that failed to produce a heartbeat".
const GUARD_CACHE = "sd-nav-guard";
const GUARD_KEY = "https://source-deterrent.invalid/nav-count";

const alive = new Set(); // client ids that proved they can run JS
const nudged = new Set(); // client ids already navigated once

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function navCount() {
  try {
    const cache = await caches.open(GUARD_CACHE);
    const hit = await cache.match(GUARD_KEY);
    if (!hit) return 0;
    const n = parseInt(await hit.text(), 10);
    return Number.isFinite(n) ? n : 0;
  } catch {
    // Fail CLOSED. A budget that cannot be read cannot be enforced, and an
    // unbounded navigate loop is far worse than the feature not firing.
    return MAX_NAVIGATIONS;
  }
}

async function setNavCount(n) {
  try {
    const cache = await caches.open(GUARD_CACHE);
    await cache.put(GUARD_KEY, new Response(String(n)));
  } catch {
    // Unwritable; navCount() fails closed on the next read.
  }
}

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("message", (e) => {
  if (e.data !== PING || !e.source) return;
  alive.add(e.source.id);
  // A heartbeat proves JS runs here, so the consecutive-failure budget resets.
  e.waitUntil(setNavCount(0));
});

async function sweep(resultingClientId) {
  if ((await navCount()) >= MAX_NAVIGATIONS) return;

  // Read the nav count and resolve the client in parallel with the grace sleep
  // so both are ready the moment the timer fires.
  const [, client] = await Promise.all([
    sleep(GRACE_MS),
    resultingClientId ? self.clients.get(resultingClientId) : Promise.resolve(null),
  ]);

  let clients = [];
  if (client) {
    clients = [client];
  } else {
    // resultingClientId is not populated in every context. Falling back to a
    // full sweep is safe ONLY because we are already behind the marker gate:
    // an uninstrumented document never schedules a sweep in the first place.
    clients = await self.clients.matchAll({
      type: "window",
      includeUncontrolled: true,
    });
  }

  for (const c of clients) {
    if (alive.has(c.id) || nudged.has(c.id)) continue;

    // A navigated client comes back with a NEW id, so per-id marking alone
    // cannot stop a loop. The persisted counter is what actually bounds it.
    const n = await navCount();
    if (n >= MAX_NAVIGATIONS) return;
    nudged.add(c.id);
    await setNavCount(n + 1);

    try {
      await c.navigate(c.url);
    } catch {
      // Client went away, or is not navigable. Nothing to do.
    }
  }
}

self.addEventListener("fetch", (e) => {
  if (e.request.mode !== "navigate") return;

  const resultingClientId = e.resultingClientId;
  const fetched = fetch(e.request);

  // respondWith is load-bearing: it keeps the worker alive long enough for the
  // sweep to run. waitUntil on its own gets the worker killed first (tested).
  // The cost is one pass-through hop on navigations -- measure it on your app,
  // and check it does not interfere with framework data/prefetch requests.
  e.respondWith(fetched);

  e.waitUntil(
    (async () => {
      let response;
      try {
        response = await fetched;
      } catch {
        return;
      }
      // Reading headers does not consume the body, so no clone is needed.
      if (response.headers.get(MARKER) !== "1") return; // uninstrumented -> never sweep
      await sweep(resultingClientId);
    })(),
  );
});
