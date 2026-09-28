const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const ts = require('typescript');
const next = require('next/server');

function load(file, imports = {}, globals = {}) {
  const { outputText } = ts.transpileModule(readFileSync(path.join(__dirname, '..', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  });
  const exports = {};
  vm.runInNewContext(outputText, {
    exports, URL, Response, process, ...globals,
    require(name) {
      assert.ok(name in imports, `Unexpected import: ${name}`);
      return imports[name];
    },
  });
  return exports;
}

async function visit(pathname, { cookie = '', role = 'admin', status = 200, domainStatus = 200, unavailable = false, portals = '' } = {}) {
  const calls = [];
  const { middleware } = load('middleware.ts', {
    'next/server': next,
    '@/lib/prelander-session': {},
    '@/lib/entry-guard': {},
  }, {
    process: { env: { ...process.env, PORTAL_HOSTNAMES: portals } },
    async fetch(url, options) {
      calls.push({ url, options });
      if (url.includes('/domain-access')) return new Response('{"role":"portal"}', { status: domainStatus });
      assert.ok(url.endsWith('/auth/me'));
      if (unavailable) throw Error('Backend unavailable');
      return new Response(JSON.stringify({ user: { role } }), { status });
    },
  });
  const response = await middleware(new next.NextRequest(`https://portal.example${pathname}`, {
    headers: { host: 'portal.example', cookie },
  }));
  return { response, calls };
}

test('admin entry routes exist and redirect to the canonical pages', () => {
  for (const [file, destination] of [
    ['app/admin/page.tsx', '/admin/dashboard'],
    ['app/admin/login/page.tsx', '/admin/auth'],
    ['app/admin/a7b9c2d4e8f1g3h5/page.tsx', '/admin/auth'],
  ]) {
    let redirected;
    load(file, { 'next/navigation': { redirect: value => { redirected = value; } } }).default();
    assert.equal(redirected, destination);
  }
});

test('signed-out admin entry, dashboard and stats send the visitor to login', async () => {
  for (const pathname of ['/admin', '/admin/dashboard', '/admin/direct-link-stats']) {
    const { response, calls } = await visit(pathname);
    assert.equal(response.status, 307);
    assert.equal(response.headers.get('location'), 'https://portal.example/admin/auth');
    assert.equal(calls.length, 1);
  }
  for (const pathname of ['/admin/auth', '/admin/login', '/admin/a7b9c2d4e8f1g3h5']) {
    const { response } = await visit(pathname);
    assert.equal(response.headers.get('x-middleware-next'), '1');
    assert.equal(response.headers.get('location'), null);
  }
});

test('a valid backend session works with missing or damaged display cookies', async () => {
  for (const metadata of ['', '; admin_user=broken']) {
    for (const pathname of ['/admin', '/admin/direct-link-stats', '/admin/auth', '/admin/login', '/admin/a7b9c2d4e8f1g3h5']) {
      const { response, calls } = await visit(pathname, { cookie: `admin_token=valid${metadata}` });
      assert.equal(calls[1].options.headers.authorization, 'Bearer valid');
      assert.equal(calls[1].options.headers.host, 'portal.example');
      assert.equal(calls[1].options.cache, 'no-store');
      if (['/admin/auth', '/admin/login', '/admin/a7b9c2d4e8f1g3h5'].includes(pathname)) {
        assert.equal(response.headers.get('location'), 'https://portal.example/admin/dashboard');
      } else {
        assert.equal(response.headers.get('x-middleware-next'), '1');
      }
      assert.match(response.headers.get('cache-control'), /no-store/);
    }
  }
});

test('expired sessions and non-admin tokens clear cookies without a login redirect loop', async () => {
  for (const session of [{ status: 401 }, { status: 403 }, { role: 'publisher' }]) {
    for (const pathname of ['/admin/auth', '/admin/dashboard']) {
      const { response } = await visit(pathname, {
        ...session, cookie: 'admin_token=invalid; admin_user=%7B%22role%22%3A%22admin%22%7D',
      });
      assert.equal(response.headers.get('location'), pathname.endsWith('/auth') ? null : 'https://portal.example/admin/auth');
      for (const name of ['admin_token', 'admin_user', 'admin_refresh_token']) {
        assert.equal(response.cookies.get(name).value, '');
        assert.equal(response.cookies.get(name).expires.getTime(), 0);
      }
    }
  }
});

test('backend outages preserve admin sessions and report a retryable error', async () => {
  for (const session of [{ status: 503 }, { unavailable: true }]) {
    const { response } = await visit('/admin/dashboard', { cookie: 'admin_token=valid', ...session });
    assert.equal(response.status, 503);
    assert.equal(response.headers.get('set-cookie'), null);
    assert.equal(response.headers.get('location'), null);
  }
});

test('admin login cannot bypass the hostname role gate', async () => {
  const { response, calls } = await visit('/admin/auth', { cookie: 'admin_token=valid', domainStatus: 403 });
  assert.equal(response.status, 404);
  assert.equal(calls.length, 1);
});

test('configured portal login avoids a backend probe but still validates admin sessions', async () => {
  const anonymous = await visit('/admin/auth', { portals: 'portal.example' });
  assert.equal(anonymous.response.status, 200);
  assert.equal(anonymous.calls.length, 0);
  const signedIn = await visit('/admin/dashboard', { portals: 'portal.example', cookie: 'admin_token=valid' });
  assert.equal(signedIn.calls.length, 1);
  assert.ok(signedIn.calls[0].url.endsWith('/auth/me'));
  assert.equal(signedIn.response.status, 200);
  const denied = await visit('/public-stats/secret', { portals: 'portal.example', domainStatus: 403 });
  assert.equal(denied.response.status, 404);
  assert.equal(denied.calls.length, 1);
});

test('bad login credentials stay on the form; protected API 401 still logs out', async () => {
  let onError;
  const removed = [];
  const location = { pathname: '/admin/auth', href: '' };
  load('lib/api.ts', {
    axios: { default: { create: () => ({ interceptors: {
      request: { use() {} }, response: { use(_success, failure) { onError = failure; } },
    } }) } },
    'js-cookie': { default: { remove: name => removed.push(name) } },
  }, { window: { location } });
  const loginError = { response: { status: 401 }, config: { url: '/auth/login' } };
  await assert.rejects(onError(loginError), error => error === loginError);
  assert.equal(location.href, '');
  assert.deepEqual(removed, []);

  location.pathname = '/admin/dashboard';
  const sessionError = { response: { status: 401 }, config: { url: '/admin/dashboard' } };
  await assert.rejects(onError(sessionError), error => error === sessionError);
  assert.equal(location.href, '/admin/auth');
  assert.deepEqual(removed, ['admin_token', 'admin_refresh_token', 'admin_user']);
});

test('successful admin login writes credentials before a fresh dashboard navigation', async () => {
  let cursor = 0;
  const values = [false, false, ' admin@example.com ', 'test-password'];
  const events = [];
  const jsx = (type, props) => ({ type, props });
  const page = load('app/admin/auth/page.tsx', {
    react: { useState: () => [values[cursor++], () => {}] },
    'react/jsx-runtime': { jsx, jsxs: jsx },
    'lucide-react': {},
    sonner: { toast: { success() {}, error(message) { throw Error(message); } } },
    '@/lib/api': { authApi: { async login(data) {
      assert.equal(data.email, 'admin@example.com');
      assert.equal(data.password, 'test-password');
      return { data: { role: 'admin', access_token: 'access', refresh_token: 'refresh', publisher_id: 'admin-id' } };
    } } },
    '@/lib/auth': {
      setAdminTokens: (...args) => events.push(['tokens', ...args]),
      setAdminUser: user => events.push(['user', user.role]),
    },
  }, { window: { location: { replace: url => events.push(['navigate', url]) } } }).default();
  function findForm(node) {
    if (!node || typeof node !== 'object') return null;
    if (node.type === 'form') return node;
    return [node.props?.children].flat().map(findForm).find(Boolean);
  }
  await findForm(page).props.onSubmit({ preventDefault() {} });
  assert.deepEqual(events, [['tokens', 'access', 'refresh'], ['user', 'admin'], ['navigate', '/admin/dashboard']]);
});
