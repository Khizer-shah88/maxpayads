/* Run after npm run build. Uses real Next middleware and FastAPI prelander
 * routes with local in-memory stores; never contacts a production backend. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const http = require('node:http');
const { spawn } = require('node:child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const frontend = path.resolve(__dirname, '..');
const backend = path.resolve(frontend, '../ppc-backend');
const artifacts = fs.mkdtempSync(path.join(os.tmpdir(), 'maxpayads-prelander-'));
const children = [];
const results = [];
let browser;
let proxy;

async function freePort() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}

function launch(command, args, cwd, env, name) {
  const child = spawn(command, args, { cwd, env: { ...process.env, ...env }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  const log = fs.createWriteStream(path.join(artifacts, `${name}.log`));
  child.stdout.pipe(log); child.stderr.pipe(log);
  child.on('error', error => log.write(String(error)));
  children.push(child);
  return child;
}

async function ready(url, child) {
  for (let i = 0; i < 120; i++) {
    if (child.exitCode !== null) throw Error(`Server exited: ${child.exitCode}; see ${artifacts}`);
    try { await fetch(url); return; } catch {}
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw Error(`Server did not start: ${url}`);
}

async function emptyNavigation(page, target, underlying) {
  const responsePromise = page.waitForResponse(r => r.url() === underlying && r.request().isNavigationRequest());
  try { await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 15000 }); }
  catch (error) { assert.match(error.message, /ERR_ABORTED/); }
  const response = await responsePromise;
  assert.equal(response.status(), 204);
  assert.match(response.headers()['cache-control'], /no-store/);
  assert.equal(response.headers()['x-sd'], undefined);
}

(async () => {
  const apiPort = await freePort(), webPort = await freePort(), nextPort = await freePort();
  const python = process.env.PYTHON || path.join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const api = launch(python, ['-m', 'uvicorn', 'browser_prelander_fixture:app', '--app-dir', 'tests', '--host', '127.0.0.1', '--port', String(apiPort)], backend,
    { DEBUG: 'false', PRELANDER_BROWSER_PORT: String(webPort), PYTHONPATH: backend }, 'backend');
  await ready(`http://127.0.0.1:${apiPort}/browser-test/health`, api);
  const web = launch(process.execPath, [path.join(frontend, 'node_modules/next/dist/bin/next'), 'start', '-H', '127.0.0.1', '-p', String(nextPort)], frontend,
    { NEXT_BACKEND_URL: `http://127.0.0.1:${apiPort}`, PORTAL_HOSTNAMES: '127.0.0.1', ENTRY_SESSION_SECRET: '', ENABLE_SOURCE_DETERRENT: 'true' }, 'frontend');
  const base = `http://localhost:${webPort}`;
  await ready(`http://127.0.0.1:${nextPort}/`, web);
  // Match nginx's /api and /_auth routing, including Host preservation. This
  // also avoids Node-version-specific Host handling in Next's fetch proxy.
  proxy = http.createServer((request, response) => {
    const api = request.url.startsWith('/api/');
    const auth = request.url.startsWith('/_auth/') && !request.headers['x-test-auth-fallback'];
    const target = api ? request.url.slice(4) : auth ? `/prelander${request.url}` : request.url;
    const upstream = http.request({ hostname: '127.0.0.1', port: api || auth ? apiPort : nextPort,
      path: target, method: request.method, headers: request.headers }, incoming => {
      response.writeHead(incoming.statusCode, incoming.headers);
      incoming.pipe(response);
    });
    upstream.on('error', error => { response.writeHead(502); response.end(String(error)); });
    request.pipe(upstream);
  });
  await new Promise(resolve => proxy.listen(webPort, '127.0.0.1', resolve));
  browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  const documents = [], errors = [], downloads = [];
  page.on('response', r => { if (r.request().isNavigationRequest()) documents.push({ url: r.url(), status: r.status() }); });
  page.on('pageerror', e => errors.push(e.message));
  page.on('download', download => { downloads.push(download.url()); void download.cancel(); });
  await page.goto(`${base}/api/browser-test/start`);
  await page.getByRole('heading', { name: 'Authorized prelander' }).waitFor();
  assert.equal(page.url(), `${base}/`);
  assert.equal(await page.evaluate(() => window.templateScriptRan), true);
  assert.equal(await page.locator('#continue').getAttribute('href'), 'https://offer.example/selected?click=browser-test');
  assert.ok(documents.some(d => d.url === `${base}/d/session` && d.status === 200));
  results.push('Authorized handoff renders the assigned HTML template, runs its script, preserves the offer URL, and cleans the address bar.');

  await emptyNavigation(page, `view-source:${base}/`, `${base}/`);
  assert.equal(await page.title(), 'Browser fixture prelander');
  assert.equal(await page.locator('h1').innerText(), 'Authorized prelander');
  assert.equal(page.url(), `${base}/`);
  await page.screenshot({ path: path.join(artifacts, 'same-tab-view-source.png') });
  results.push('Same-tab view-source receives 204 and retains the rendered page.');

  const newTab = await context.newPage();
  await emptyNavigation(newTab, `view-source:${base}/`, `${base}/`);
  assert.equal(await newTab.locator('body').innerText(), '');
  await emptyNavigation(newTab, `${base}/`, `${base}/`);
  assert.equal(await newTab.locator('body').innerText(), '');
  results.push('New-tab view-source and direct clean-URL visits stay blank, even with the valid session cookie.');

  const fresh = await browser.newContext();
  await emptyNavigation(await fresh.newPage(), `${base}/`, `${base}/`);
  await fresh.close();
  results.push('A fresh browser without cookies also receives 204.');

  // A Chrome toolbar reload of the clean root must not replay arbitrary
  // template scripts. It receives a static inline page with no script content.
  const reloadContext = await browser.newContext();
  const reloadPage = await reloadContext.newPage();
  const reloadDownloads = [];
  reloadPage.on('download', download => { reloadDownloads.push(download.url()); void download.cancel(); });
  await reloadPage.goto(`${base}/api/browser-test/start`);
  await reloadPage.getByRole('heading', { name: 'Authorized prelander' }).waitFor();
  const reloaded = reloadPage.waitForResponse(r => r.url() === `${base}/` && r.request().isNavigationRequest());
  try { await reloadPage.reload({ waitUntil: 'domcontentloaded' }); } catch (e) { assert.match(e.message, /ERR_ABORTED/); }
  const reloadResponse = await reloaded;
  assert.equal(reloadResponse.status(), 200);
  assert.equal(reloadResponse.headers()['content-disposition'], 'inline');
  assert.match(await reloadPage.locator('body').innerText(), /cannot be reopened by refreshing/i);
  assert.deepEqual(reloadDownloads, []);
  await reloadContext.close();
  results.push('Chrome reload of the clean prelander root receives a script-free inline page and triggers no download.');

  // An already-installed legacy worker must not turn 204 into a replay loop.
  await page.evaluate(async () => { await navigator.serviceWorker.register('/source-deterrent-sw.js'); await navigator.serviceWorker.ready; });
  await emptyNavigation(page, `${base}/`, `${base}/`);
  await emptyNavigation(page, `view-source:${base}/`, `${base}/`);
  const count = documents.length;
  await page.waitForTimeout(1200);
  assert.equal(documents.length, count);
  assert.equal(await page.locator('h1').innerText(), 'Authorized prelander');
  results.push('An installed legacy service worker passes through 204 without replaying the arrival.');

  await page.route('https://offer.example/**', route => route.fulfill({ contentType: 'text/html', body: '<h1>Selected offer reached</h1>' }));
  await page.locator('#continue').click();
  await page.getByRole('heading', { name: 'Selected offer reached' }).waitFor();
  results.push('The existing template button still opens the selected offer (intercepted locally).');

  const builtin = await context.newPage();
  await builtin.goto(`${base}/api/browser-test/start?variant=windows`);
  await builtin.getByRole('heading', { name: 'Built-in prelander' }).waitFor();
  assert.equal(builtin.url(), `${base}/`);
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: base });
  await builtin.getByRole('button', { name: 'Copy' }).click();
  assert.equal(await builtin.evaluate(() => navigator.clipboard.readText()), 'https://offer.example/selected?click=browser-test');
  results.push('The built-in template renders at the cleaned URL and its Copy button keeps the selected offer.');

  await context.request.post(`${base}/api/browser-test/revoke`);
  assert.equal((await context.request.get(`${base}/api/prelander/resolve/session`)).status(), 403);
  assert.equal((await context.request.get(`${base}/d/session`)).status(), 403);
  assert.equal((await context.request.get(`${base}/`)).status(), 204);
  results.push('Revoked sessions cannot fetch content or load the entry route; the clean root remains 204.');
  assert.equal((await context.request.get(`http://127.0.0.1:${webPort}/`)).status(), 200);
  results.push('The portal hostname still serves its normal root page.');

  const fallbackContext = await browser.newContext({ extraHTTPHeaders: { 'x-test-auth-fallback': '1' } });
  const fallbackPage = await fallbackContext.newPage();
  await fallbackPage.goto(`${base}/api/browser-test/start`);
  await fallbackPage.getByRole('heading', { name: 'Authorized prelander' }).waitFor();
  assert.equal(fallbackPage.url(), `${base}/`);
  await fallbackContext.close();
  results.push('Next middleware handoff recovery also reaches the entry route and renders correctly.');
  assert.deepEqual(errors, []);
  assert.deepEqual(downloads, []);
  fs.writeFileSync(path.join(artifacts, 'results.json'), JSON.stringify({ results, documents, errors, downloads }, null, 2));
  results.forEach(result => console.log(`PASS ${result}`));
  console.log(`Artifacts: ${artifacts}`);
})().catch(error => { console.error(error); console.error(`Artifacts: ${artifacts}`); process.exitCode = 1; })
  .finally(async () => {
    if (browser) await browser.close();
    if (proxy) { proxy.closeAllConnections(); await new Promise(resolve => proxy.close(resolve)); }
    for (const child of children.reverse()) child.kill();
  });
