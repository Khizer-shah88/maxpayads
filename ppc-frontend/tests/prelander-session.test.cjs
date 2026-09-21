const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

// Compile the real modules, including the inline shell, without starting Next.
function loadModule(file, imports = {}) {
  const source = readFileSync(path.join(__dirname, '..', file), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  });
  const exports = {};
  vm.runInNewContext(outputText, {
    exports, Response, process,
    require(name) {
      assert.ok(name in imports, `Unexpected import: ${name}`);
      return imports[name];
    },
  });
  return exports;
}

const tab = loadModule('lib/tab-guard.ts');
const session = loadModule('lib/prelander-session.ts');
// PRELANDER_TEST_BUILD=1 also checks serialization after Next's minification.
const shell = process.env.PRELANDER_TEST_BUILD === '1'
  ? require('../.next/server/app/clean-shell/route.js').routeModule.userland
  : loadModule('app/clean-shell/route.ts', {
  '@/lib/tab-guard': tab,
  '@/lib/prelander-session': session,
  '@/lib/source-deterrent-script': { sourceDeterrentScriptTag: () => '' },
});

function browser({ referrer = '', historyLength = 1, marker = null, storageBlocked = false,
  claim = new Response(JSON.stringify({ ok: false, reason: 'arrival_unavailable' }), { status: 403 }),
  resolve = new Response(JSON.stringify({ success: true, rendered_html: '<h1>Authorized</h1>' })) } = {}) {
  const events = [];
  const root = { hidden: true, style: {}, replaceChildren(...children) { this.children = children; } };
  const location = { hostname: 'landing.example', pathname: '/', search: '',
    replace(url) { events.push(['replace', url]); } };
  const history = { length: historyLength, back() { events.push(['back']); } };
  const document = {
    referrer, title: '', getElementById: () => root,
    createElement: () => ({}),
    open() {}, write(html) { events.push(['render', html]); }, close() {},
  };
  const context = {
    URL, document, location, history,
    window: { location, history },
    sessionStorage: {
      getItem() { if (storageBlocked) throw Error('Storage blocked'); return marker; },
      setItem(key, value) { if (storageBlocked) throw Error('Storage blocked'); marker = value; },
    },
    async fetch(url) {
      events.push(['fetch', url]);
      const response = url.endsWith('/claim') ? claim : resolve;
      if (response instanceof Error) throw response;
      return response.clone();
    },
    setTimeout() { throw Error('Navigation must not depend on timers'); },
  };
  return { context, events, root, document };
}

async function runShell(options) {
  const b = browser(options);
  const response = await shell.GET();
  const html = await response.text();
  assert.doesNotMatch(html, /pl-loader|pl-spin|Loading&hellip;|Redirecting&hellip;/);
  assert.match(response.headers.get('cache-control'), /no-store/);
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  await vm.runInNewContext(script, b.context);
  return b;
}

test('pasted tab immediately returns to its external referrer without resolving content', async () => {
  const b = await runShell({ referrer: 'https://previous.example/page', historyLength: 2 });
  assert.deepEqual(b.events, [['fetch', '/api/prelander/claim'], ['replace', 'https://previous.example/page']]);
  assert.equal(b.root.hidden, true);
});

test('address-bar paste returns through history without timers', async () => {
  const b = await runShell({ historyLength: 2 });
  assert.deepEqual(b.events, [['fetch', '/api/prelander/claim'], ['back']]);
});

test('fresh pasted tab with no previous page shows session expired', async () => {
  const b = await runShell();
  assert.equal(b.document.title, session.SESSION_UNAVAILABLE_TITLE);
  assert.equal(b.root.hidden, false);
  assert.deepEqual(b.events, [['fetch', '/api/prelander/claim']]);
});

for (const storageBlocked of [false, true]) {
  test(`missing/expired session shows the same message with storage blocked=${storageBlocked}`, async () => {
    const b = await runShell({ storageBlocked, historyLength: 2, referrer: 'https://previous.example/',
      claim: new Response(JSON.stringify({ ok: false }), { status: 403 }) });
    assert.equal(b.document.title, session.SESSION_UNAVAILABLE_TITLE);
    assert.equal(b.root.children[1].textContent, session.SESSION_UNAVAILABLE_MESSAGE);
    assert.deepEqual(b.events, [['fetch', '/api/prelander/claim']]);
  });

  test(`legitimate arrival renders with storage blocked=${storageBlocked}`, async () => {
    const b = await runShell({ storageBlocked, claim: new Response('{"ok":true}') });
    assert.deepEqual(b.events, [
      ['fetch', '/api/prelander/claim'], ['fetch', '/api/prelander/resolve/session'],
      ['render', '<h1>Authorized</h1>'],
    ]);
  });
}

test('reload with a tab marker still validates the server session', async () => {
  const b = await runShell({ marker: '1', resolve: new Response('{}', { status: 403 }) });
  assert.equal(b.document.title, session.SESSION_UNAVAILABLE_TITLE);
  assert.deepEqual(b.events, [['fetch', '/api/prelander/resolve/session']]);
});

test('valid reload does not consume another arrival claim', async () => {
  const b = await runShell({ marker: '1' });
  assert.deepEqual(b.events, [['fetch', '/api/prelander/resolve/session'], ['render', '<h1>Authorized</h1>']]);
});

for (const referrer of ['https://landing.example/old', 'javascript:alert(1)', 'invalid']) {
  test(`unsafe or same-host referrer cannot become a redirect: ${referrer}`, async () => {
    const b = await runShell({ referrer });
    assert.equal(b.document.title, session.SESSION_UNAVAILABLE_TITLE);
    assert.deepEqual(b.events, [['fetch', '/api/prelander/claim']]);
  });
}

for (const claim of [new Response('{}', { status: 503 }), new Error('offline')]) {
  test(`claim failure denies access: ${claim.status || claim.message}`, async () => {
    const b = await runShell({ claim });
    assert.equal(b.document.title, session.SESSION_UNAVAILABLE_TITLE);
    assert.deepEqual(b.events, [['fetch', '/api/prelander/claim']]);
  });
}

test('concurrent React effects consume one arrival', async () => {
  const b = browser({ claim: new Response('{"ok":true}') });
  const guard = vm.runInNewContext(`(${tab.createTabGuard.toString()})()`, b.context);
  const first = guard();
  assert.equal(guard(), first);
  assert.equal(await first, 'allowed');
  assert.deepEqual(b.events, [['fetch', '/api/prelander/claim']]);
});
