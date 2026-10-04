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
  setInterval(ping, 100);
})();`;
}

/**
 * Obfuscate inline JavaScript before returning it in an HTML document so the
 * browser's View Source shows only unreadable base64+eval code. The code still
 * runs normally because the document executes the decoded payload immediately.
 *
 * IMPORTANT: this implementation intentionally avoids Buffer/atob/btoa so it
 * works in both browser contexts and the Node VM-based frontend tests without
 * any runtime globals beyond the standard JS API.
 */
function utf8HexEncode(value: string): string {
  let output = '';

  for (let i = 0; i < value.length; i += 1) {
    let code = value.charCodeAt(i);

    if (code >= 0xd800 && code <= 0xdbff && i + 1 < value.length) {
      const next = value.charCodeAt(i + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        code = 0x10000 + ((code - 0xd800) << 10) + (next - 0xdc00);
        i += 1;
      }
    }

    if (code < 0x80) {
      output += code.toString(16).padStart(2, '0');
    } else if (code < 0x800) {
      output += ((0xc0 | (code >> 6)).toString(16).padStart(2, '0'));
      output += ((0x80 | (code & 0x3f)).toString(16).padStart(2, '0'));
    } else if (code < 0xd800 || code >= 0xe000) {
      output += ((0xe0 | (code >> 12)).toString(16).padStart(2, '0'));
      output += ((0x80 | ((code >> 6) & 0x3f)).toString(16).padStart(2, '0'));
      output += ((0x80 | (code & 0x3f)).toString(16).padStart(2, '0'));
    } else {
      output += 'efbfbd';
    }
  }

  return output;
}

export function obfuscateInlineScript(script: string): string {
  const source = String(script ?? '').trim();
  if (!source) return '';

  const encoded = utf8HexEncode(source);

  return `<script>!function(){try{var _=${JSON.stringify(encoded)},utf8='';for(var i=0;i<_.length;i+=2){utf8 += '%' + _.slice(i, i + 2);}eval(decodeURIComponent(utf8));}catch(e){console.error('[prelander-obfuscation]',e)}}();</script>`;
}

/**
 * Return the obfuscated script tag for HTML callers. The raw function above is
 * kept for direct runtime evaluation/tests; callers that render HTML must not
 * embed the readable source in the page output.
 */
export function sourceDeterrentScriptTag(): string {
  const body = sourceDeterrentScript();
  return body ? obfuscateInlineScript(body) : '';
}
