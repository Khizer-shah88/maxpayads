/**
 * Source-View Deterrent Service Worker
 *
 * EXPLICIT NON-GOAL: This does not and cannot prevent access to the source.
 * curl and every other HTTP client, DevTools -> Network -> Response,
 * DevTools Elements, "Save page as", and the very first visit before the
 * service worker installs all still show everything. The HTML is already on
 * the client. It deters a casual Cmd/Ctrl+U and nothing more. It is NOT a
 * security control -- secrets still belong server-side.
 *
 * HOW IT WORKS
 * A view-source: tab cannot execute JavaScript, so it never sends the heartbeat
 * that the page sends. Nothing in the API exposes the "view-source:" prefix --
 * request.url and client.url both read as the plain URL -- so the tab is
 * identified by ABSENCE. Any window client still silent after GRACE_MS is
 * navigated to its own url, which re-opens it as an ordinary document; the
 * prefix does not survive.
 *
 * This fires on any JS-less context, not specifically on view-source.
 *
 * VERIFIED IN CHROME. Firefox/Safari behaviour for SW-visible view-source
 * navigations and client.navigate() is untested -- treat as "feature absent".
 */

// Heartbeat message the page posts to prove it can run JavaScript.
const PING = 'heartbeat';

// Grace period from navigation to first heartbeat, tuned to the p95 on the
// slowest supported device/network plus headroom. Too low bounces real users
// whose JS is merely slow; too high leaves the source readable that long.
const GRACE_MS = 1200;

// Loop guard -- the most important lines here. A visitor who genuinely cannot
// run JS (JS disabled, hydration crash, blocked inline script, extension
// interference) must NOT be navigated forever. A client that cannot be "fixed"
// is left alone on a readable page.
const MAX_NAVIGATIONS = 3;

const alive = new Set();   // client ids that proved they can run JS
const nudged = new Set();  // client ids already navigated once
let navigations = 0;       // total across all clients, this worker's lifetime

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('message', (e) => {
  if (e.data === PING && e.source) alive.add(e.source.id);
});

async function sweep() {
  if (navigations >= MAX_NAVIGATIONS) return;

  await sleep(GRACE_MS);

  const clients = await self.clients.matchAll({
    type: 'window',
    includeUncontrolled: true,
  });

  for (const client of clients) {
    if (alive.has(client.id) || nudged.has(client.id)) continue;
    if (navigations >= MAX_NAVIGATIONS) return;

    // A navigated client comes back with a NEW id, so per-id marking alone
    // cannot stop a loop -- the global counter is what actually bounds it.
    nudged.add(client.id);
    navigations += 1;

    try {
      // Navigating a JS-less client to its own url re-opens it as a normal
      // document. The view-source: prefix does not survive.
      await client.navigate(client.url);
    } catch {
      // Client went away, or is not navigable. Nothing to do.
    }
  }
}

self.addEventListener('fetch', (e) => {
  // Only navigation requests matter; leave data/prefetch/asset fetches alone.
  if (e.request.mode !== 'navigate') return;

  // respondWith is load-bearing: it keeps the worker alive long enough for the
  // sweep to run. waitUntil on its own gets the worker killed first (tested).
  // The cost is one pass-through hop on navigations.
  e.respondWith(fetch(e.request));
  e.waitUntil(sweep());
});
