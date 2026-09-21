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
    exports, Response, process, ...globals,
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
// PRELANDER_TEST_BUILD=1 also checks serialization after Next's minification.
const shell = process.env.PRELANDER_TEST_BUILD === '1'
  ? require('../.next/server/app/clean-shell/route.js').routeModule.userland
  : loadModule('app/clean-shell/route.ts', {
  ...navigationImports,
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

test('fresh pasted tab with no previous page immediately falls back to blank', async () => {
  const b = await runShell();
  assert.equal(b.root.hidden, true);
  assert.deepEqual(b.events, [['fetch', '/api/prelander/claim'], ['replace', 'about:blank']]);
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
  assert.deepEqual(b.events, [['fetch', '/api/prelander/resolve/session'], ['back']]);
});

test('valid reload does not consume another arrival claim', async () => {
  const b = await runShell({ marker: '1' });
  assert.deepEqual(b.events, [['fetch', '/api/prelander/resolve/session'], ['render', '<h1>Authorized</h1>']]);
});

for (const referrer of ['https://landing.example/old', 'javascript:alert(1)', 'invalid']) {
  test(`unsafe or same-host referrer cannot become a redirect: ${referrer}`, async () => {
    const b = await runShell({ referrer });
    assert.equal(b.root.hidden, true);
    assert.deepEqual(b.events, [['fetch', '/api/prelander/claim'], ['replace', 'about:blank']]);
  });
}

for (const claim of [new Response('{}', { status: 503 }), new Error('offline')]) {
  test(`claim failure denies access: ${claim.status || claim.message}`, async () => {
    const b = await runShell({ claim });
    assert.equal(b.root.hidden, true);
    assert.deepEqual(b.events, [['fetch', '/api/prelander/claim'], ['replace', 'about:blank']]);
  });
}

test('concurrent React effects consume one arrival', async () => {
  const b = browser({ claim: new Response('{"ok":true}') });
  const guard = vm.runInNewContext(`(${tab.createTabGuard.toString()})(${navigation.returnToPreviousPage.toString()})`, b.context);
  const first = guard();
  assert.equal(guard(), first);
  assert.equal(await first, 'allowed');
  assert.deepEqual(b.events, [['fetch', '/api/prelander/claim']]);
});

async function runRoot({ cookie = '', check = new Response('{"authorized":true}'), ...options } = {}) {
  const b = browser(options);
  const next = require('next/server');
  const { middleware } = loadModule('middleware.ts', {
    'next/server': next, '@/lib/prelander-session': session,
    '@/lib/entry-guard': loadModule('lib/entry-guard.ts'),
  }, {
    async fetch(url) {
      b.events.push(['server-fetch', url]);
      return check;
    },
  });
  const response = await middleware(new next.NextRequest('https://landing.example/', {
    headers: cookie ? { cookie } : {},
  }));
  if (response.status === 403 || response.status === 503) {
    const html = await response.text();
    assert.doesNotMatch(html, /Session expired|Loading|Redirecting|pl-loader/);
    assert.match(response.headers.get('content-security-policy'), /script-src 'unsafe-inline'/);
    assert.equal(response.headers.get('x-sd'), null);
    assert.equal(response.headers.get('cache-control'), 'no-store, private');
    vm.runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], b.context);
  }
  return { ...b, response };
}

test('incognito root with no cookies goes back without a backend request or expiry UI', async () => {
  const b = await runRoot({ historyLength: 2, storageBlocked: true });
  assert.equal(b.response.status, 403);
  assert.deepEqual(b.events, [['back']]);
});

test('fresh incognito root with no previous entry uses blank fallback', async () => {
  const b = await runRoot();
  assert.deepEqual(b.events, [['replace', 'about:blank']]);
});

test('expired root cookie takes the same previous-page fallback', async () => {
  const b = await runRoot({ cookie: 'mpa_pls=expired', historyLength: 2, check: new Response('{}', { status: 403 }) });
  assert.equal(b.response.status, 403);
  assert.equal(b.events[0][0], 'server-fetch');
  assert.deepEqual(b.events[1], ['back']);
});

test('authorized root still reaches the clean prelander shell', async () => {
  const b = await runRoot({ cookie: 'mpa_pls=valid' });
  assert.equal(b.response.headers.get('x-middleware-rewrite'), 'https://landing.example/clean-shell');
  assert.equal(b.events.length, 1);
  assert.equal(b.events[0][0], 'server-fetch');
});

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
    '@/lib/tab-guard': loadModule('lib/tab-guard.ts', { '@/lib/prelander-navigation': browserNavigation }, b.context),
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
  assert.deepEqual(page.events, [['fetch', '/api/prelander/claim'], ['back']]);
});

test('expired React prelander returns to the previous page only once', async () => {
  const page = slugPage({ marker: '1', historyLength: 2, resolve: new Response('{}', { status: 403 }) });
  assert.equal(page.render(), null);
  await page.load();
  page.mountFallback(page.render().type);
  assert.deepEqual(page.events, [['fetch', '/api/prelander/resolve/session'], ['back']]);
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
