const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const ts = require('typescript');

// Exercise the actual page's handlers and rendered JSX without a browser or production API.
function pageHarness({ loadError = false, saveError = false } = {}) {
  const states = [];
  const effects = [];
  const saved = [];
  const errors = [];
  let cursor = 0;
  let mounted = false;
  const domains = [
    { id: 'domain-a', domain: 'first.example', template_id: 'custom', status: 'active' },
    { id: 'domain-b', domain: 'second.example', template_id: null, status: 'active' },
  ];
  const jsx = (type, props) => ({ type, props });
  const imports = {
    react: {
      useState(initial) {
        const index = cursor++;
        if (!mounted) states[index] = initial;
        return [states[index], value => { states[index] = typeof value === 'function' ? value(states[index]) : value; }];
      },
      useEffect(effect) { if (!mounted) effects.push(effect); },
      useCallback(callback) { return callback; },
    },
    'react/jsx-runtime': { jsx, jsxs: jsx },
    'lucide-react': {},
    sonner: { toast: { error: message => errors.push(message), success() {} } },
    '@/components/shared/Sidebar': { default: () => null },
    '@/components/ui/ConfirmDialog': { default: () => null },
    '@/components/ui/badge': { StatusBadge: () => null },
    '@/components/ui/loading': { Spinner: () => null },
    '@/lib/hooks/useAuth': { useAuth: () => ({ initialize() {} }) },
    '@/lib/api': {
      adminApi: {
        async getRedirectionDomains(params) {
          assert.equal(params.domain_type, 'prelander');
          if (loadError) throw new Error('offline');
          return { data: { domains: domains.map(d => ({ ...d })) } };
        },
      },
      prlanderTemplateApi: {
        async getAll() {
          return { data: { templates: [{
            id: 'custom', name: 'Custom template', status: 'active', usage_count: 0,
            assigned_domains: domains.filter(d => d.template_id === 'custom').map(d => ({ ...d })),
          }] } };
        },
        async assignDomains(id, domainIds) {
          if (saveError) throw new Error('offline');
          saved.push({ id, domainIds: [...domainIds] });
          domains.forEach(d => { d.template_id = domainIds.includes(d.id) ? id : null; });
        },
      },
    },
  };
  const source = readFileSync(path.join(__dirname, '../app/admin/prelander-templates/page.tsx'), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  });
  const exports = {};
  vm.runInNewContext(outputText, { exports, require(name) { assert.ok(name in imports, name); return imports[name]; } });
  return {
    saved, errors,
    render() { cursor = 0; const tree = exports.default(); mounted = true; return tree; },
    async load() { effects.forEach(effect => effect()); await new Promise(resolve => setImmediate(resolve)); },
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
  const result = nodes(tree).find(node => node.type === 'button' && text(node) === label);
  assert.ok(result, `Button ${label} is present`);
  return result;
}

test('template page restores assignments, saves changed domains, and refreshes its card', async () => {
  const page = pageHarness();
  page.render();
  await page.load();
  await button(page.render(), ' Assign Domains').props.onClick();
  let inputs = nodes(page.render()).filter(node => node.type === 'input' && node.props.type === 'checkbox');
  assert.deepEqual(inputs.map(node => node.props.checked), [true, false]);
  inputs[0].props.onChange({ target: { checked: false } });
  inputs[1].props.onChange({ target: { checked: true } });
  await button(page.render(), 'Save Assignments').props.onClick();
  assert.deepEqual(page.saved, [{ id: 'custom', domainIds: ['domain-b'] }]);
  assert.match(text(page.render()), /second\.example/);
  assert.doesNotMatch(text(page.render()), /first\.example/);
  await button(page.render(), ' Assign Domains').props.onClick();
  inputs = nodes(page.render()).filter(node => node.type === 'input' && node.props.type === 'checkbox');
  assert.deepEqual(inputs.map(node => node.props.checked), [false, true]);
});

test('failed domain loading cannot submit an empty selection', async () => {
  const page = pageHarness({ loadError: true });
  page.render();
  await page.load();
  await button(page.render(), ' Assign Domains').props.onClick();
  assert.ok(page.errors.includes('Failed to load prelander domains'));
  assert.ok(!nodes(page.render()).some(node => node.props?.role === 'dialog'));
  assert.deepEqual(page.saved, []);
});

test('failed save keeps the assignment dialog open for retry', async () => {
  const page = pageHarness({ saveError: true });
  page.render();
  await page.load();
  await button(page.render(), ' Assign Domains').props.onClick();
  await button(page.render(), 'Save Assignments').props.onClick();
  assert.ok(page.errors.includes('Failed to save assignments'));
  assert.equal(button(page.render(), 'Save Assignments').props.disabled, false);
  assert.ok(nodes(page.render()).some(node => node.props?.role === 'dialog'));
  assert.deepEqual(page.saved, []);
});
