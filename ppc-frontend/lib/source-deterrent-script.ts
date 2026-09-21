/**
 * The source-view deterrent's page script — ONE definition, used by every
 * instrumented document.
 *
 * It previously existed twice, implemented differently: the clean shell pinged
 * `navigator.serviceWorker.controller` while /d/[slug] pinged
 * `registration.active/waiting/installing` and logged on every 400ms tick.
 * Two copies of a heartbeat is how you end up with pages that look instrumented
 * but are not, which is exactly the shape of the bug that reload-looped
 * visitors. There is now one source of truth.
 *
 * MUST be inlined into server-delivered HTML, never bundled. If it shipped in a
 * bundle and the bundle failed to load, the page would fall silent and the
 * worker would navigate it — firing on precisely the users it should leave
 * alone.
 *
 * Any document that embeds this MUST also carry the `x-sd: 1` response header
 * (set in middleware.ts), or the worker will not sweep it. A document carrying
 * the header WITHOUT this script is the dangerous combination: that is a
 * guaranteed reload loop. Keep the two together.
 *
 * Reference implementation: ~/view-source-demo/source-deterrent/snippet.html
 * This is not a security control. See SOURCE_DETERRENT.md.
 */

/** True when the deterrent is switched on for this deployment. */
export function sourceDeterrentEnabled(): boolean {
  return process.env.ENABLE_SOURCE_DETERRENT === 'true';
}

/**
 * Local verification escape hatch. Service workers run on localhost (it counts
 * as a secure context), but shipping the deterrent there would leak the worker
 * into every other project sharing the dev port. Requires BOTH a development
 * build AND an explicit opt-in, so it cannot be switched on in production even
 * by accident.
 */
function allowLocalhost(): boolean {
  return (
    process.env.NODE_ENV === 'development' &&
    process.env.SOURCE_DETERRENT_ALLOW_LOCALHOST === 'true'
  );
}

/**
 * Returns the inline script body, or '' when the feature is off — in which case
 * callers embed nothing at all.
 */
export function sourceDeterrentScript(): string {
  if (!sourceDeterrentEnabled()) return '';

  // Body follows ~/view-source-demo/source-deterrent/snippet.html. The PING
  // string must stay identical to the worker's PING constant.
  return `(function () {
  if (!('serviceWorker' in navigator)) return;

  // Service workers require a secure context. A plain-http staging host gets no
  // feature at all -- by design, not by accident.
  if (!window.isSecureContext) return;
  ${allowLocalhost()
    ? '// SOURCE_DETERRENT_ALLOW_LOCALHOST=true — localhost skip disabled for local verification.'
    : "// Never run in local development: it interferes with reading your own source.\n  if (['localhost', '127.0.0.1', '[::1]'].indexOf(location.hostname) !== -1) return;"}

  navigator.serviceWorker.register('/source-deterrent-sw.js', { scope: '/' }).catch(function () {});

  function ping() {
    var controller = navigator.serviceWorker.controller;
    if (controller) controller.postMessage('SOURCE_DETERRENT_PING');
  }
  // Ping immediately, again once a worker is controlling this page, then keep
  // proving liveness. The interval must be well under the worker's GRACE_MS.
  // (controllerchange is an addition to the reference: it closes the gap on the
  // very first load, where the worker starts controlling after ready resolves.)
  ping();
  navigator.serviceWorker.ready.then(ping);
  navigator.serviceWorker.addEventListener('controllerchange', ping);
  setInterval(ping, 50);
})();`;
}

/** The same script wrapped in a <script> tag, for raw-HTML callers. */
export function sourceDeterrentScriptTag(): string {
  const body = sourceDeterrentScript();
  return body ? `<script>\n${body}\n</script>` : '';
}
