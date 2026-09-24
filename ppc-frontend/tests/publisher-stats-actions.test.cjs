const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const ts = require('typescript');

const source = readFileSync(path.join(__dirname, '../app/admin/direct-link-stats/page.tsx'), 'utf8');
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
});

function pageHarness({ failSetup = false } = {}) {
  const states = [], effects = [], calls = [], errors = [];
  let cursor = 0, mounted = false;
  const publishers = Array.from({ length: 8 }, (_, i) => ({
    id: `pub-${i}`, name: `Publisher ${i}`, email: `manual${i}@manual.invalid`, role: 'publisher', status: 'active',
  }));
  const links = publishers.slice(0, 4).map(pub => ({
    id: `link-${pub.id}`, publisher_id: pub.id, status: 'active', total_clicks: 0,
    total_conversions: 0, today_conversions: 0, stats_domain: '', preferences: {},
  }));
  const copy = value => JSON.parse(JSON.stringify(value));
  const jsx = (type, props) => ({ type, props });
  const imports = {
    react: {
      useState(initial) {
        const index = cursor++;
        if (!mounted) states[index] = typeof initial === 'function' ? initial() : initial;
        return [states[index], value => { states[index] = typeof value === 'function' ? value(states[index]) : value; }];
      },
      useEffect(effect) { if (!mounted) effects.push(effect); },
      useCallback(callback) { return callback; },
    },
    'react/jsx-runtime': { jsx, jsxs: jsx },
    'lucide-react': {},
    sonner: { toast: { error: message => errors.push(message), success() {} } },
    '@/components/shared/Sidebar': { default: () => null },
    '@/components/ui/badge': { StatusBadge: () => null },
    '@/components/ui/loading': { Spinner: () => null },
    '@/lib/hooks/useAuth': { useAuth: () => ({ initialize() {} }) },
    '@/lib/api': {
      adminApi: {
        async getPublishers() { return { data: { publishers: copy(publishers) } }; },
        async getPublisher(id) { return { data: { publisher: { public_id: `PUB_${id}` } } }; },
        async getStatsDomain() { return { data: {} }; },
      },
      directLinkApi: {
        async getAll() { return { data: { links: copy(links) } }; },
        async getPublisherDomains() { return { data: { publisher_domains: [] } }; },
        async ensurePublisherStatsLink(pid) {
          calls.push(['ensure', pid]);
          if (failSetup) throw { response: { data: { detail: 'Setup unavailable' } } };
          let link = links.find(l => l.publisher_id === pid);
          if (!link) {
            link = { id: `link-${pid}`, publisher_id: pid, status: 'paused', stats_domain: '', preferences: {} };
            links.push(link);
          }
          return { data: { link: copy(link) } };
        },
        async update(id, data) {
          calls.push(['update', id, copy(data)]);
          Object.assign(links.find(l => l.id === id), copy(data));
          return { data: {} };
        },
        async shareStatsLink(id) {
          calls.push(['share', id]);
          return { data: { stats_url: `https://stats.example/public-stats/${id}` } };
        },
        async regenerateStatsLink(id) {
          calls.push(['regenerate', id]);
          return { data: { stats_url: `https://stats.example/public-stats/new-${id}` } };
        },
        async listManualConversions({ publisher_id }) {
          calls.push(['history', publisher_id]);
          return { data: { conversions: [] } };
        },
      },
    },
  };
  const exports = {};
  vm.runInNewContext(outputText, { exports, console, URL, require(name) { assert.ok(name in imports, name); return imports[name]; } });
  return {
    calls, errors, links,
    render() { cursor = 0; const tree = exports.default(); mounted = true; return tree; },
    async load() { effects.forEach(effect => effect()); await this.flush(); },
    async flush() { await new Promise(resolve => setImmediate(resolve)); },
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

function button(tree, label) {
  const result = nodes(tree).find(n => n.type === 'button' && (n.props.title === label || text(n) === label));
  assert.ok(result, `Button '${label}' is present`);
  assert.ok(!result.props.disabled, `Button '${label}' is enabled`);
  return result;
}

for (const [title, expected] of [
  ['Share stats link', 'Publisher Stats Link'],
  ['Stats preferences', 'Stats Page Preferences'],
  ['Dedicated stats domain', 'Dedicated Stats Domain'],
  ['Conversion history', 'Conversion History'],
  ['Regenerate stats link', 'Publisher Stats Link'],
]) {
  test(`${title} works as the first action for every existing and newly added publisher`, async () => {
    for (let i = 0; i < 8; i++) {
      const page = pageHarness();
      page.render();
      await page.load();
      const tree = page.render();
      const rows = nodes(tree).filter(n => n.type === 'tr' && n.props.onClick);
      assert.equal(rows.length, 8, 'Publishers without links must be visible');
      await button(rows[i], title).props.onClick();
      assert.ok(text(page.render()).includes(expected), `${expected} opens for publisher ${i}`);
      assert.deepEqual(page.errors, []);
      assert.ok(page.calls.some(([action, id]) => action === (title === 'Conversion history' ? 'history' : 'ensure') && id === `pub-${i}`));
    }
  });
}

test('new publisher preferences and domain save to the resolved stats record', async () => {
  const page = pageHarness();
  page.render();
  await page.load();
  const row = () => nodes(page.render()).find(n => n.type === 'tr' && n.props.onClick && text(n).includes('Publisher 7'));
  await button(row(), 'Stats preferences').props.onClick();
  const label = nodes(page.render()).find(n => n.type === 'label' && text(n).startsWith('Show Mac Valid Clicks'));
  nodes(label).find(n => n.type === 'button').props.onClick();
  await button(page.render(), 'Save Preferences').props.onClick();
  await page.flush();
  assert.equal(page.links.find(l => l.publisher_id === 'pub-7').preferences.show_mac_clicks, true);

  await button(row(), 'Dedicated stats domain').props.onClick();
  const modal = nodes(page.render()).find(n => n.type === 'div' && n.props.className?.includes('fixed inset-0') && text(n).includes('Dedicated Stats Domain'));
  const input = nodes(modal).find(n => n.type === 'input');
  assert.ok(input);
  input.props.onChange({ target: { value: 'reports.example' } });
  const updatedModal = nodes(page.render()).find(n => n.type === 'div' && n.props.className?.includes('fixed inset-0') && text(n).includes('Dedicated Stats Domain'));
  await button(updatedModal, 'Save Domain').props.onClick();
  await page.flush();
  assert.equal(page.links.find(l => l.publisher_id === 'pub-7').stats_domain, 'reports.example');
  assert.deepEqual(page.errors, []);
});

test('failed setup shows an error and restores action buttons for retry', async () => {
  const page = pageHarness({ failSetup: true });
  page.render();
  await page.load();
  const row = () => nodes(page.render()).filter(n => n.type === 'tr' && n.props.onClick)[7];
  for (const title of ['Stats preferences', 'Dedicated stats domain', 'Share stats link', 'Regenerate stats link']) {
    await button(row(), title).props.onClick();
    assert.equal(page.errors.at(-1), 'Setup unavailable');
    button(row(), title);
  }
  assert.equal(page.links.length, 4);
});
