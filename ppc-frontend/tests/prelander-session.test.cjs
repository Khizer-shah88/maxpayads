const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

// Compile the real modules, including the inline shell, without starting Next.
function loadModule(file, imports = {}, globals = {}) {
  const source = readFileSync(path.join(__dirname, '..', file), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  });
  const exports = {};
  vm.runInNewContext(outputText, {
    exports, Response, URL, process, ...globals,
    require(name) {
      assert.ok(name in imports, `Unexpected import: ${name}`);
      return imports[name];
    },
  });
  return exports;
}

const navigation = loadModule('lib/prelander-navigation.ts');
const navigationImports = { '@/lib/prelander-navigation': navigation };
const tab = loadModule('lib/tab-guard.ts', navigationImports);
const session = loadModule('lib/prelander-session.ts', navigationImports);
const chromeReloadGuard = function installChromePrelanderReloadGuard() {};
// PRELANDER_TEST_BUILD=1 also checks serialization after Next's minification.
const shell = process.env.PRELANDER_TEST_BUILD === '1'
  ? require('../.next/server/app/clean-shell/route.js').routeModule.userland
  : loadModule('app/clean-shell/route.ts', {
  ...navigationImports,
  '@/lib/tab-guard': tab,
  '@/lib/prelander-session': session,
  '@/lib/chrome-prelander-reload-guard': { installChromePrelanderReloadGuard: chromeReloadGuard },
  '@/lib/source-deterrent-script': { sourceDeterrentScriptTag: () => '' },
});

function browser({ referrer = '', historyLength = 1, marker = null, storageBlocked = false,
  claim = new Response(JSON.stringify({ ok: false, reason: 'arrival_unavailable' }), { status: 403 }),
  resolve = new Response(JSON.stringify({ success: true, rendered_html: '<h1>Authorized</h1>' })) } = {}) {
  const events = [];
  const root = { hidden: true, style: {}, addEventListener() {}, replaceChildren(...children) { this.children = children; } };
  const location = { hostname: 'landing.example', pathname: '/', search: '',
    replace(url) { events.push(['replace', url]); } };
  const history = { length: historyLength,
    replaceState(_state, _title, url) { location.pathname = url; location.search = ''; },
    back() { throw Error('Back can close an in-app browser'); } };
  const document = {
    referrer, title: '', getElementById: () => root,
    querySelector: () => null,
    createElement: () => ({ setAttribute() {} }),
    head: { appendChild(link) { events.push(['favicon', link.href]); } },
    open() {}, write(html) { events.push(['render', html]); }, close() {},
  };
  const context = {
    URL, document, location, history,
    window: { location, history, close() { throw Error('Must keep the browser open'); } },
    sessionStorage: {
      getItem() { if (storageBlocked) throw Error('Storage blocked'); return marker; },
      setItem(key, value) { if (storageBlocked) throw Error('Storage blocked'); marker = value; },
    },
    async fetch(url) {
      if (context.fetchOverride) return context.fetchOverride(url);
      events.push(['fetch', url]);
      const response = url.endsWith('/claim') ? claim : resolve;
      if (response instanceof Error) throw response;
      return response.clone();
    },
    setTimeout(...args) {
      if (context.setTimeoutOverride) return context.setTimeoutOverride(...args);
      throw Error('Navigation must not depend on timers');
    },
  };
  return { context, events, root, document };
}

async function runShell(options) {
  const b = browser(options);
  const response = await shell.GET();
  const html = await response.text();
  assert.doesNotMatch(html, /pl-loader|pl-spin|Loading&hellip;|Redirecting&hellip;|Session expired/);
  assert.match(response.headers.get('cache-control'), /no-store/);
  const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
  await vm.runInNewContext(script, b.context);
  return b;
}

test('clean shell emits valid JavaScript before any session request', async () => {
  const html = await (await shell.GET()).text();
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  assert.ok(scripts.length);
  for (const [, script] of scripts) assert.doesNotThrow(() => new vm.Script(script));
});

for (const os of ['windows', 'mac']) {
  test(`authorized ${os} arrival reveals the built-in prelander`, async () => {
    const b = await runShell({ claim: new Response('{"ok":true}'),
      resolve: new Response(JSON.stringify({ success: true, os,
        offer_url: 'https://download.example/file', template: { title: 'Your download' } })) });
    assert.equal(b.root.hidden, false);
    assert.match(b.root.innerHTML, /Your download/);
    assert.match(b.root.innerHTML, /https:\/\/download.example\/file/);
    assert.equal(b.events.some(([event]) => event === 'replace' || event === 'back'), false);
  });
}

for (const favicon of ['https://cdn.example/icon.png', 'cdn[.]example/icon.png',
  '<link rel="icon" href="https://cdn.example/icon.png">']) {
  test(`favicon parsing preserves prelander rendering: ${favicon}`, async () => {
    const b = await runShell({ claim: new Response('{"ok":true}'),
      resolve: new Response(JSON.stringify({ success: true, rendered_html: '<h1>Authorized</h1>',
        template: { favicon_url: favicon } })) });
    assert.deepEqual(b.events.slice(-2), [
      ['favicon', 'https://cdn.example/icon.png'], ['render', '<h1>Authorized</h1>'],
    ]);
  });
}

test('pasted tab immediately returns to its external referrer without resolving content', async () => {
  const b = await runShell({ referrer: 'https://previous.example/page', historyLength: 2 });
  assert.deepEqual(b.events, [['fetch', '/api/prelander/claim'], ['replace', 'https://previous.example/page']]);
  assert.equal(b.root.hidden, true);
});

test('address-bar paste with history uses configured fallback without going back', async () => {
  const b = await runShell({ historyLength: 2 });
  assert.deepEqual(b.events, [['fetch', '/api/prelander/claim'], ['replace', '/prelander-fallback']]);
});

test('fresh pasted tab with no previous page uses the configured fallback', async () => {
  const b = await runShell();
  assert.equal(b.root.hidden, true);
  assert.deepEqual(b.events, [['fetch', '/api/prelander/claim'], ['replace', '/prelander-fallback']]);
});

for (const storageBlocked of [false, true]) {
  test(`missing/expired session goes back with storage blocked=${storageBlocked}`, async () => {
    const b = await runShell({ storageBlocked, historyLength: 2, referrer: 'https://previous.example/',
      claim: new Response(JSON.stringify({ ok: false }), { status: 403 }) });
    assert.equal(b.root.hidden, true);
    assert.deepEqual(b.events, [['fetch', '/api/prelander/claim'], ['replace', 'https://previous.example/']]);
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
  const b = await runShell({ marker: '1', historyLength: 2, resolve: new Response('{}', { status: 403 }) });
  assert.equal(b.root.hidden, true);
  assert.deepEqual(b.events, [['fetch', '/api/prelander/resolve/session'], ['replace', '/prelander-fallback']]);
});

test('valid reload does not consume another arrival claim', async () => {
  const b = await runShell({ marker: '1' });
  assert.deepEqual(b.events, [['fetch', '/api/prelander/resolve/session'], ['render', '<h1>Authorized</h1>']]);
});

for (const referrer of ['https://landing.example/old', 'javascript:alert(1)', 'invalid',
  'https://inter.example/d/h_consumed', 'https://other.example/_auth/used',
  'https://other.example/prelander-fallback', 'https://user:pass@previous.example/']) {
  test(`unsafe or same-host referrer cannot become a redirect: ${referrer}`, async () => {
    const b = await runShell({ referrer });
    assert.equal(b.root.hidden, true);
    assert.deepEqual(b.events, [['fetch', '/api/prelander/claim'], ['replace', '/prelander-fallback']]);
  });
}

for (const claim of [new Response('{}', { status: 503 }), new Error('offline')]) {
  test(`claim outage stays on a recoverable page: ${claim.status || claim.message}`, async () => {
    const b = await runShell({ claim });
    assert.equal(b.root.hidden, false);
    assert.match(b.root.innerHTML, /Temporarily unavailable/);
    assert.deepEqual(b.events, [['fetch', '/api/prelander/claim']]);
  });
}

test('temporary resolve failure keeps the claimed tab available for a reload', async () => {
  const b = await runShell({ claim: new Response('{"ok":true}'),
    resolve: new Response('{}', { status: 503 }), referrer: 'https://inter.example/' });
  assert.match(b.root.innerHTML, /Try again/);
  assert.deepEqual(b.events, [['fetch', '/api/prelander/claim'], ['fetch', '/api/prelander/resolve/session']]);
  assert.equal(b.context.sessionStorage.getItem('pl_tab_ok'), '1');
});

test('concurrent React effects consume one arrival', async () => {
  const b = browser({ claim: new Response('{"ok":true}') });
  const guard = vm.runInNewContext(`(${tab.createTabGuard.toString()})(${navigation.returnToPreviousPage.toString()})`, b.context);
  const first = guard();
  assert.equal(guard(), first);
  assert.equal(await first, 'allowed');
  assert.deepEqual(b.events, [['fetch', '/api/prelander/claim']]);
});

async function runRoot({ cookie = '', path = '/', role = 'prelander', headers = {},
  check = new Response('{"authorized":true}'), ...options } = {}) {
  const b = browser(options);
  const next = require('next/server');
  const { middleware } = loadModule('middleware.ts', {
    'next/server': next, '@/lib/prelander-session': session,
    '@/lib/entry-guard': loadModule('lib/entry-guard.ts'),
  }, {
    async fetch(url) {
      if (url.includes('/domain-access')) return new Response(JSON.stringify({ role }));
      b.events.push(['server-fetch', url]);
      return check;
    },
  });
  const response = await middleware(new next.NextRequest(`https://landing.example${path}`, {
    headers: { ...headers, ...(cookie ? { cookie } : {}) },
  }));
  if (response.status === 503) {
    assert.match(await response.text(), /Session expired or unavailable/);
    assert.equal(response.headers.get('x-sd'), null);
  } else if (response.status === 403) {
    const html = await response.text();
    assert.doesNotMatch(html, /Session expired|Loading|Redirecting|pl-loader/);
    assert.match(response.headers.get('content-security-policy'), /script-src 'unsafe-inline'/);
    assert.equal(response.headers.get('x-sd'), null);
    assert.equal(response.headers.get('cache-control'), 'no-store, private');
    vm.runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], b.context);
  }
  return { ...b, response };
}

for (const cookie of ['', 'mpa_pls=valid', 'mpa_pls=expired']) {
  test(`clean root returns empty uncached 204 regardless of session: ${cookie || 'private browser'}`, async () => {
    const b = await runRoot({ cookie, storageBlocked: true, headers: { 'sec-fetch-site': 'none' } });
    assert.equal(b.response.status, 204);
    assert.equal(await b.response.text(), '');
    assert.equal(b.response.headers.get('location'), null);
    assert.equal(b.response.headers.get('x-sd'), null);
    assert.match(b.response.headers.get('content-type'), /text\/html/);
    assert.match(b.response.headers.get('cache-control'), /no-store/);
    assert.deepEqual(b.events, []);
  });
}

test('portal root remains a normal page', async () => {
  const b = await runRoot({ role: 'portal' });
  assert.equal(b.response.status, 200);
  assert.equal(b.response.headers.get('x-middleware-next'), '1');
});

for (const path of ['/d/session', '/clean-shell']) {
  test(`entry requires a valid cookie: ${path}`, async () => {
    assert.equal((await runRoot({ path })).response.status, 403);
    const expired = await runRoot({ path, cookie: 'mpa_pls=expired', check: new Response('{}', { status: 403 }) });
    assert.equal(expired.response.status, 403);
    assert.equal(expired.response.headers.get('x-middleware-rewrite'), null);
  });
}

test('authorized clean-shell destination continues without rewriting itself', async () => {
  const b = await runRoot({ path: '/clean-shell', cookie: 'mpa_pls=valid' });
  assert.equal(b.response.headers.get('x-middleware-next'), '1');
  assert.equal(b.response.headers.get('x-middleware-rewrite'), null);
});

for (const configured of ['https://fallback.example/previous', '', 'javascript:alert(1)',
  'https://landing.example/', 'https://user:pass@fallback.example/',
  'https://fallback.example/prelander-fallback', 'invalid']) {
  test(`server fallback uses a safe configured destination: ${configured}`, async () => {
    const next = require('next/server');
    const env = { ENTRY_FALLBACK_URL: configured, ENABLE_SOURCE_DETERRENT: 'true' };
    const entry = loadModule('lib/entry-guard.ts', {}, { process: { env } });
    const { middleware } = loadModule('middleware.ts', {
      'next/server': next, '@/lib/prelander-session': session, '@/lib/entry-guard': entry,
    }, {
      process: { env },
      fetch() { throw Error('Fallback must work without the backend'); },
    });
    const response = await middleware(new next.NextRequest('https://landing.example/prelander-fallback?url=https://untrusted.example/'));
    assert.equal(response.status, 302);
    assert.equal(response.headers.get('location'), 'https://www.google.com/');
    assert.equal(response.headers.get('cache-control'), 'no-store, private');
    assert.equal(response.headers.get('x-sd'), null);
  });
}

test('session-check outage does not send visitors back into the redirect chain', async () => {
  const b = await runRoot({ path: '/d/session', cookie: 'mpa_pls=valid', check: new Response('{}', { status: 503 }),
    referrer: 'https://inter.example/' });
  assert.equal(b.response.status, 503);
  assert.deepEqual(b.events.map(([event]) => event), ['server-fetch']);
});

for (const site of ['none', 'cross-site', 'same-site', 'same-origin']) {
  test(`authorized entry reaches the shell with navigation metadata ${site}`, async () => {
    const b = await runRoot({ path: '/d/session', cookie: 'mpa_pls=valid', headers: { 'sec-fetch-site': site } });
    assert.equal(b.response.headers.get('x-middleware-rewrite'), 'https://landing.example/clean-shell');
    assert.equal(b.events.length, 1);
    assert.equal(b.events[0][0], 'server-fetch');
  });
}

test('clean-root flow never opts into legacy service-worker navigation', async () => {
  const next = require('next/server');
  const { middleware } = loadModule('middleware.ts', {
    'next/server': next, '@/lib/prelander-session': session,
    '@/lib/entry-guard': loadModule('lib/entry-guard.ts'),
  }, {
    process: { env: { ENABLE_SOURCE_DETERRENT: 'true' } },
    async fetch(url, init) {
      const host = init?.headers ? new Headers(init.headers).get('host') || '' : '';
      if (url.includes('/domain-access')) {
        return new Response(JSON.stringify({ role: host.includes('inter.example') ? 'inter' : 'prelander' }));
      }
      return new Response('{"authorized":true}');
    },
  });
  for (const path of ['/', '/d/h_ticket', '/d/session', '/clean-shell']) {
    const response = await middleware(new next.NextRequest(`https://landing.example${path}`, {
      headers: { cookie: 'mpa_pls=valid' },
    }));
    assert.equal(response.status, path === '/' ? 204 : 200);
    assert.equal(response.headers.get('x-sd'), null, path);
  }
});

test('inter root never renders the portal shell and falls back immediately', async () => {
  const b = await runRoot({
    role: 'inter',
    check: new Response('{"role":"inter"}'),
    referrer: 'https://facebook.com/',
  });
  assert.equal(b.response.status, 403);
  assert.deepEqual(b.events, [['replace', 'https://facebook.com/']]);
});

test('view-source requests are redirected back to the regular page with a permanent redirect on prelander domains only', async () => {
  const next = require('next/server');
  const { middleware } = loadModule('middleware.ts', {
    'next/server': next, '@/lib/prelander-session': session,
    '@/lib/entry-guard': loadModule('lib/entry-guard.ts'),
  }, {
    process: { env: { ENABLE_SOURCE_DETERRENT: 'true' } },
    async fetch(url, init) {
      const host = init?.headers ? new Headers(init.headers).get('host') || '' : '';
      if (url.includes('/domain-access')) {
        return new Response(JSON.stringify({ role: host.includes('inter.example') ? 'inter' : 'prelander' }));
      }
      return new Response('{"authorized":true}');
    },
  });
  const response = await middleware(new next.NextRequest('view-source:https://landing.example/prelander', {
    headers: { host: 'landing.example' },
  }));
  assert.equal(response.status, 301);
  assert.equal(response.headers.get('location'), 'https://landing.example/prelander');
  assert.equal(response.headers.get('cache-control'), 'no-store, private');

  const inter = await middleware(new next.NextRequest('view-source:https://inter.example/', {
    headers: { host: 'inter.example' },
  }));
  assert.equal(inter.status, 200);
});


for (const site of ['none', 'cross-site', 'same-site', 'same-origin']) {
  test(`Inter ticket reached from a smartlink is not rejected by navigation metadata: ${site}`, async () => {
    const next = require('next/server');
    const { middleware } = loadModule('middleware.ts', {
      'next/server': next, '@/lib/prelander-session': session,
      '@/lib/entry-guard': loadModule('lib/entry-guard.ts'),
    }, {
      process: { env: { ENABLE_SOURCE_DETERRENT: 'true' } },
      fetch: async () => new Response('{"role":"inter"}'),
    });
    const response = await middleware(new next.NextRequest('https://inter.example/d/h_issued_ticket', {
      headers: { 'sec-fetch-site': site, 'sec-fetch-mode': 'navigate', 'sec-fetch-dest': 'document' },
    }));
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('x-middleware-next'), '1');
    assert.equal(response.headers.get('x-sd'), null);
  });
}

for (const [role, path] of [['prelander', '/d/copied_slug'],
  ['prelander', '/d/h_copied_ticket'], ['inter', '/d/copied_slug']]) {
  test(`pasted protected pages still take the fallback: ${role} ${path}`, async () => {
    const next = require('next/server');
    const { middleware } = loadModule('middleware.ts', {
      'next/server': next, '@/lib/prelander-session': session,
      '@/lib/entry-guard': loadModule('lib/entry-guard.ts'),
    }, { fetch: async () => new Response(JSON.stringify({ role })) });
    const response = await middleware(new next.NextRequest(`https://${role}.example${path}`, {
      headers: { 'sec-fetch-site': 'none', 'sec-fetch-mode': 'navigate', 'sec-fetch-dest': 'document' },
    }));
    assert.equal(response.status, 403);
    assert.match(await response.text(), /prelander-fallback/);
  });
}

// Exercise the React page's state transitions without introducing a test-only
// DOM dependency. Render actual JSX and flush its asynchronous load effect.
function slugPage({ slug = 'session', ...options } = {}) {
  const b = browser(options);
  const effects = [];
  const states = [];
  let cursor = 0;
  let mounted = false;
  const jsx = (type, props) => ({ type, props });
  const browserNavigation = loadModule('lib/prelander-navigation.ts', {}, b.context);
  const Page = loadModule('app/d/[slug]/page.tsx', {
    'react': {
      useRef(initial) { return { current: initial }; },
      useState(initial) {
        const index = cursor++;
        if (!mounted) states[index] = initial;
        return [states[index], value => { states[index] = value; }];
      },
      useEffect(effect) { if (!mounted) effects.push(effect); },
    },
    'react/jsx-runtime': { jsx, jsxs: jsx },
    'next/navigation': { useParams: () => ({ slug }) },
    'lucide-react': {},
    '@/lib/prelander-navigation': browserNavigation,
    '@/lib/prelander-favicon': loadModule('lib/prelander-favicon.ts', {}, b.context),
    '@/lib/tab-guard': loadModule('lib/tab-guard.ts', { '@/lib/prelander-navigation': browserNavigation }, b.context),
    // Reload protection is installed only when custom HTML is rendered; these
    // state-transition tests do not emulate a browser navigation lifecycle.
    '@/lib/chrome-prelander-reload-guard': { installChromePrelanderReloadGuard: chromeReloadGuard },
  }, b.context).default;
  return {
    ...b,
    render() { cursor = 0; const result = Page(); mounted = true; return result; },
    async load() { effects.forEach(effect => effect()); await new Promise(resolve => setImmediate(resolve)); },
    mountFallback(Component) {
      mounted = false;
      assert.equal(Component(), null);
      mounted = true;
      // React strict mode runs the mounted effect twice.
      effects.at(-1)();
      effects.at(-1)();
    },
  };
}

test('React prelander fallback has no redirect-flow loader', async () => {
  const page = slugPage({ historyLength: 2 });
  assert.equal(page.render(), null);
  await page.load();
  assert.equal(page.render(), null);
  assert.deepEqual(page.events, [['fetch', '/api/prelander/claim'], ['replace', '/prelander-fallback']]);
});

test('expired React prelander returns to the previous page only once', async () => {
  const page = slugPage({ marker: '1', historyLength: 2, resolve: new Response('{}', { status: 403 }) });
  assert.equal(page.render(), null);
  await page.load();
  page.mountFallback(page.render().type);
  assert.deepEqual(page.events, [['fetch', '/api/prelander/resolve/session'], ['replace', '/prelander-fallback']]);
});

test('React session outage shows recovery without returning to the Inter root', async () => {
  const page = slugPage({ marker: '1', resolve: new Response('{}', { status: 503 }),
    referrer: 'https://inter.example/' });
  page.render();
  await page.load();
  assert.equal(page.render().props.role, 'alert');
  assert.deepEqual(page.events, [['fetch', '/api/prelander/resolve/session']]);
});

for (const nextUrl of ['https://next-inter.example/d/h_next', 'https://landing.example/_auth/one-use',
  'https://campaign.example/download']) {
  test(`authorized Inter ticket follows its recorded destination: ${nextUrl}`, async () => {
    const page = slugPage({ slug: 'h_issued_ticket' });
    page.context.fetchOverride = async (url) => {
      page.events.push(['fetch', url]);
      assert.equal(url, '/api/prelander/hop/h_issued_ticket');
      return new Response(JSON.stringify({ next_url: nextUrl }));
    };
    page.context.setTimeoutOverride = (callback) => callback();
    page.render();
    await page.load();
    assert.deepEqual(page.events, [['fetch', '/api/prelander/hop/h_issued_ticket'], ['replace', nextUrl]]);
  });
}

test('invalid or consumed Inter ticket still redirects to fallback without rendering content', async () => {
  const page = slugPage({ slug: 'h_consumed' });
  page.context.fetchOverride = async () => new Response('{}', { status: 403 });
  page.render();
  await page.load();
  assert.equal(page.render(), null);
  assert.deepEqual(page.events, [['replace', '/prelander-fallback']]);
});

for (const decision of [{ bypass_redirect_url: 'https://offer.example/' }, { prelander_domain: 'https://landing.example' }]) {
  test(`confirmed redirect domain displays its loader: ${Object.keys(decision)[0]}`, async () => {
    const page = slugPage({ slug: 'flow-slug' });
    page.context.fetchOverride = async url => {
      if (url.includes('/domain-type')) return new Response(JSON.stringify(decision));
      return new Response('{"handoff":"one-time-token"}');
    };
    // Keep the legitimate redirect dwell pending while inspecting its UI.
    page.context.setTimeoutOverride = () => {};
    assert.equal(page.render(), null);
    await page.load();
    assert.equal(page.render()?.props.role, 'status');
    assert.match(JSON.stringify(page.render()), /Redirecting/);
  });
}
