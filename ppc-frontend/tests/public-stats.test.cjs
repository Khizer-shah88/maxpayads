const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const ts = require('typescript');

const { outputText } = ts.transpileModule(readFileSync(path.join(__dirname, '../app/public-stats/[publisherId]/page.tsx'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
});

function report(count = 1) {
  return {
    identity: { link_number: 1, pub_id: 'PUB_PRIVATE' },
    total_impressions: 20, total_conversions: 2,
    unique_windows_clicks: count, unique_mac_clicks: 2, unique_android_clicks: 3,
    preferences: { show_windows_clicks: true, show_mac_clicks: true, show_android_clicks: true },
    daily_breakdown: [{ date: '2026-09-24', clicks: 20, windows_clicks: count, mac_clicks: 2, android_clicks: 3, conversions: 2 }],
  };
}

function harness(initial = report()) {
  const slots = [], effects = [], cleanups = [], timers = new Map();
  let cursor = 0, mounted = false, requests = 0, timerId = 0;
  let respond = async () => initial;
  const jsx = (type, props) => ({ type, props });
  const imports = {
    react: {
      useState(value) {
        const index = cursor++;
        if (!mounted) slots[index] = typeof value === 'function' ? value() : value;
        return [slots[index], next => { slots[index] = typeof next === 'function' ? next(slots[index]) : next; }];
      },
      useRef(value) {
        const index = cursor++;
        if (!mounted) slots[index] = { current: value };
        return slots[index];
      },
      useEffect(effect) { if (!mounted) effects.push(effect); },
      useCallback(callback) { return callback; },
    },
    'react/jsx-runtime': { jsx, jsxs: jsx },
    'next/navigation': { useParams: () => ({ publisherId: 'secret-share' }) },
    'lucide-react': {},
    '@/lib/api': { publicStatsApi: { async getPublisherStats(id) {
      assert.equal(id, 'secret-share');
      requests++;
      return { data: { data: await respond() } };
    } } },
  };
  const exports = {};
  vm.runInNewContext(outputText, {
    exports, console, URLSearchParams,
    window: { location: { search: '?linkName=Private+link&publisherName=Private+publisher&publisherId=PUB_PRIVATE' } },
    setInterval(callback, ms) { timers.set(++timerId, { callback, ms }); return timerId; },
    clearInterval(id) { timers.delete(id); },
    require(name) { assert.ok(name in imports, name); return imports[name]; },
  });
  return {
    timers,
    get requests() { return requests; },
    respondWith(callback) { respond = callback; },
    render() { cursor = 0; const tree = exports.default(); mounted = true; return tree; },
    async mount() { this.render(); effects.forEach(effect => cleanups.push(effect())); await this.flush(); },
    tick() { timers.forEach(timer => timer.callback()); },
    async flush() { await new Promise(resolve => setImmediate(resolve)); },
    unmount() { cleanups.forEach(cleanup => cleanup?.()); },
  };
}

function nodes(tree) {
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  if (!tree || typeof tree !== 'object') return [];
  return [tree, ...nodes(tree.props?.children)];
}

function text(tree) {
  if (Array.isArray(tree)) return tree.map(text).join('');
  if (tree && typeof tree === 'object') return text(tree.props?.children);
  return typeof tree === 'string' || typeof tree === 'number' ? String(tree) : '';
}

function filters(tree) {
  return nodes(tree).find(n => n.props?.['aria-label'] === 'Operating system filters');
}

test('header hides publisher identity and OS filters appear in the stats body', async () => {
  const page = harness();
  await page.mount();
  const tree = page.render();
  const header = nodes(tree).find(n => n.type === 'header');
  const main = nodes(tree).find(n => n.type === 'main');
  assert.doesNotMatch(text(tree), /Private publisher|Private link|PUB_PRIVATE|#L1/);
  assert.doesNotMatch(text(header), /Windows|Mac|Android/);
  assert.ok(filters(main));
  assert.match(text(filters(main)), /Windows1Mac2Android3/);
});

test('30-second refresh updates in place, preserves filters, skips overlap and clears its timer', async () => {
  const page = harness();
  await page.mount();
  assert.equal(page.requests, 1);
  assert.deepEqual([...page.timers.values()].map(t => t.ms), [30000]);
  const windows = nodes(filters(page.render())).find(n => n.type === 'button' && text(n).startsWith('Windows'));
  windows.props.onClick();
  let finish;
  page.respondWith(() => new Promise(resolve => { finish = resolve; }));
  page.tick();
  assert.equal(page.requests, 2);
  const pending = page.render();
  assert.ok(nodes(pending).some(n => n.type === 'main'), 'Report stays visible while refreshing');
  assert.equal(nodes(pending).find(n => n.props?.['aria-label'] === 'Refresh stats').props.disabled, true);
  page.tick();
  assert.equal(page.requests, 2, 'Do not overlap an unfinished request');
  finish(report(4));
  await page.flush();
  const refreshedWindows = nodes(filters(page.render())).find(n => n.type === 'button' && text(n).startsWith('Windows'));
  assert.equal(text(refreshedWindows), 'Windows4');
  assert.equal(refreshedWindows.props['aria-pressed'], true);
  page.unmount();
  assert.equal(page.timers.size, 0);
});

test('temporary refresh errors retain the report and recover on the next interval', async () => {
  const page = harness();
  await page.mount();
  page.respondWith(async () => { throw new Error('offline'); });
  page.tick();
  await page.flush();
  assert.ok(nodes(page.render()).some(n => n.type === 'main'));
  assert.match(text(page.render()), /Retrying automatically/);
  page.respondWith(async () => report(8));
  page.tick();
  await page.flush();
  assert.match(text(filters(page.render())), /Windows8/);
  assert.doesNotMatch(text(page.render()), /Retrying automatically|expired/);
});

test('expired links hide cached stats at the next refresh', async () => {
  const page = harness();
  await page.mount();
  page.respondWith(async () => { throw { response: { status: 410 } }; });
  page.tick();
  await page.flush();
  assert.match(text(page.render()), /This statistics link has expired/);
  assert.ok(!nodes(page.render()).some(n => n.type === 'main'));
});

test('zero valid counts stay zero and hidden OS types have no filter or table column', async () => {
  const data = report(0);
  data.preferences.show_mac_clicks = false;
  data.preferences.show_android_clicks = false;
  const page = harness(data);
  await page.mount();
  const tree = page.render();
  assert.match(text(filters(tree)), /Windows0/);
  assert.doesNotMatch(text(tree), /Valid Mac|Valid Android/);
  assert.doesNotMatch(text(filters(tree)), /Mac|Android/);
  const day = nodes(tree).find(n => n.type === 'tbody');
  assert.ok(nodes(day).some(n => n.type === 'td' && text(n) === '0'));
});
