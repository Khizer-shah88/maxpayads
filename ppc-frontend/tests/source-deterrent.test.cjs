const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const workerSource = readFileSync(path.join(__dirname, '../public/source-deterrent-sw.js'), 'utf8');
const pageModule = {};
vm.runInNewContext(ts.transpileModule(
  readFileSync(path.join(__dirname, '../lib/source-deterrent-script.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
).outputText, { exports: pageModule, process: { env: { ENABLE_SOURCE_DETERRENT: 'true' } } });
const flush = () => new Promise(resolve => setImmediate(resolve));

function worker({ store = new Map(), cacheUnavailable = false } = {}) {
  const handlers = {};
  const timers = [];
  const clients = new Map();
  const navigations = [];
  const writes = [];
  let now = 0;
  const context = {
    Response,
    setTimeout(fn, delay) { timers.push({ fn, at: now + delay }); },
    fetch: async request => new Response('html', { headers: request.marked ? { 'x-sd': '1' } : {} }),
    caches: {
      async open() {
        if (cacheUnavailable) throw Error('Cache unavailable');
        return {
          async match(key) { return store.has(key) ? new Response(store.get(key)) : undefined; },
          async put(key, response) {
            const value = await response.text();
            writes.push(value);
            store.set(key, value);
            if (context.onWrite) await context.onWrite(value);
          },
        };
      },
    },
    self: {
      addEventListener(name, handler) { handlers[name] = handler; },
      clients: { get: async id => clients.get(id), matchAll: async () => [...clients.values()] },
    },
  };
  vm.runInNewContext(workerSource, context);
  return {
    context, navigations, writes, store,
    async ping(id) {
      let task;
      handlers.message({ data: 'SOURCE_DETERRENT_PING', source: { id }, waitUntil(p) { task = p; } });
      await task;
    },
    async navigate(id, marked = true) {
      clients.set(id, { id, url: 'https://landing.example/', navigate(url) { navigations.push({ id, url, at: now }); } });
      let task;
      handlers.fetch({
        request: { mode: 'navigate', marked }, resultingClientId: id,
        respondWith() {}, waitUntil(p) { task = p; },
      });
      await flush();
      return { task };
    },
    async advance(ms) {
      now += ms;
      for (const timer of timers.splice(0)) {
        if (timer.at <= now) timer.fn();
        else timers.push(timer);
      }
      await flush();
    },
  };
}

test('silent marked document gets the full restored 300ms wait', async () => {
  const w = worker();
  const navigation = await w.navigate('source');
  await w.advance(299);
  assert.equal(w.navigations.length, 0);
  await w.advance(1);
  await navigation.task;
  assert.deepEqual(w.navigations, [{ id: 'source', url: 'https://landing.example/', at: 300 }]);
});

test('normal page starting after 250ms is not prematurely redirected', async () => {
  const w = worker();
  const navigation = await w.navigate('normal');
  await w.advance(250);
  assert.equal(w.navigations.length, 0);
  await w.ping('normal');
  await w.advance(50);
  await navigation.task;
  assert.equal(w.navigations.length, 0);
});

test('heartbeat arriving during the budget write still prevents navigation', async () => {
  const w = worker();
  w.context.onWrite = async value => { if (value === '1') await w.ping('normal'); };
  const navigation = await w.navigate('normal');
  await w.advance(300);
  await navigation.task;
  assert.equal(w.navigations.length, 0);
});

test('frequent heartbeats do not repeatedly write the navigation budget', async () => {
  const w = worker();
  for (let i = 0; i < 10; i++) await w.ping('normal');
  assert.deepEqual(w.writes, ['0']);
});

test('unmarked fallback document is never redirected', async () => {
  const w = worker();
  const navigation = await w.navigate('fallback', false);
  await w.advance(1000);
  await navigation.task;
  assert.equal(w.navigations.length, 0);
});

test('reload budget still stops after three navigations across worker restarts', async () => {
  const store = new Map();
  let count = 0;
  for (let i = 0; i < 5; i++) {
    const w = worker({ store });
    const navigation = await w.navigate(`silent-${i}`);
    await w.advance(300);
    await navigation.task;
    count += w.navigations.length;
  }
  assert.equal(count, 3);
});

test('unavailable budget storage cannot trigger a redirect loop', async () => {
  const w = worker({ cacheUnavailable: true });
  const navigation = await w.navigate('silent');
  await w.advance(300);
  await navigation.task;
  assert.equal(w.navigations.length, 0);
});

test('page pings immediately, on controller change, and every 100ms', async () => {
  const messages = [];
  const listeners = {};
  const intervals = [];
  vm.runInNewContext(pageModule.sourceDeterrentScript(), {
    window: { isSecureContext: true }, location: { hostname: 'landing.example' },
    navigator: { serviceWorker: {
      register: async () => ({}), ready: Promise.resolve(),
      controller: { postMessage(value) { messages.push(value); } },
      addEventListener(name, callback) { listeners[name] = callback; },
    } },
    setInterval(fn, ms) { intervals.push({ fn, ms }); },
  });
  assert.equal(messages.length, 1);
  await flush();
  assert.equal(messages.length, 2);
  listeners.controllerchange();
  assert.equal(messages.length, 3);
  assert.equal(intervals[0].ms, 100);
  intervals[0].fn();
  assert.equal(messages.length, 4);
  assert.ok(messages.every(message => message === 'SOURCE_DETERRENT_PING'));
});
