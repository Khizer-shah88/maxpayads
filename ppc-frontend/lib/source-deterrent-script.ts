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
 * 
 * Enhanced with Firefox view-source detection: Firefox doesn't support service
 * workers in view-source tabs, so we add immediate DOM manipulation checks that
 * fail in view-source and redirect the page.
 */
export function sourceDeterrentScript(): string {
  if (!sourceDeterrentEnabled()) return '';
  
  const localhostGuard = allowLocalhost()
    ? ''
    : "if(['localhost','127.0.0.1','[::1]'].indexOf(location.hostname)!==-1)return;";
  
  // Enhanced Firefox view-source detection
  // In view-source, document.write and DOM manipulation fail silently
  return `(function(){if(!('serviceWorker' in navigator))return;if(!window.isSecureContext)return;${localhostGuard}try{var t=document.createElement('div');t.id='_vs_check';document.body.appendChild(t);if(!document.getElementById('_vs_check')){window.location.href='https://www.google.com';return;}document.body.removeChild(t);}catch(e){window.location.href='https://www.google.com';return;}navigator.serviceWorker.register('/source-deterrent-sw.js',{scope:'/'}).catch(function(){});function ping(){var c=navigator.serviceWorker.controller;if(c)c.postMessage('SOURCE_DETERRENT_PING');}ping();navigator.serviceWorker.ready.then(ping);navigator.serviceWorker.addEventListener('controllerchange',ping);setInterval(ping,100);})();`;
}

/** The same script wrapped in a <script> tag, for raw-HTML callers. */
export function sourceDeterrentScriptTag(): string {
  const body = sourceDeterrentScript();
  return body ? `<script>\n${body}\n</script>` : '';
}
