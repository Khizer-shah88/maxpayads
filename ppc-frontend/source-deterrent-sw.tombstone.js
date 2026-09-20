/**
 * Source-View Deterrent — TOMBSTONE (feature stood down).
 *
 * This file intentionally does nothing except remove itself.
 *
 * WHY: the previous version of this worker reload-looped real visitors. It
 * navigated ANY window client that had not sent a heartbeat within the grace
 * period, but the heartbeat only ever shipped on two pages (/d/[slug] and the
 * clean prelander shell). Every other document on the origin -- above all the
 * session-unavailable 403 page, which carries no script AND a
 * `default-src 'none'` CSP so it *cannot* run one -- was silent by
 * construction, got navigated, came back silent, and was navigated again.
 *
 * The MAX_NAVIGATIONS cap did not hold it: the counter was a module-level
 * variable, and the browser terminates an idle service worker between sweeps.
 * Every restart reset the count to 0, so the loop resumed indefinitely.
 *
 * A worker with NO fetch handler cannot sweep and cannot navigate anything, so
 * installing this file stops the loop the moment it activates. It then
 * unregisters itself, and the next navigation is served with no worker at all.
 *
 * DO NOT add handlers here. The repaired implementation lives at
 * ppc-frontend/source-deterrent-sw.repaired.js and is deliberately NOT served;
 * see SOURCE_DETERRENT.md before putting it back.
 */

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      await self.clients.claim();
      await self.registration.unregister();
    })(),
  );
});
