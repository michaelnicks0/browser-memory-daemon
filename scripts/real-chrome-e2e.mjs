#!/usr/bin/env node
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdir, rm, access, cp } from 'node:fs/promises';
import { constants as fsConstants } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), '..');

const runId = `${Date.now()}-${process.pid}`;
const defaultPortBase = 18000 + (process.pid % 2000);
const daemonPort = Number(process.env.BMD_REAL_CHROME_DAEMON_PORT || process.env.BMD_REAL_CHROME_PORT_BASE || defaultPortBase);
const pagePort = Number(process.env.BMD_REAL_CHROME_PAGE_PORT || daemonPort + 1);
const cdpPort = Number(process.env.BMD_REAL_CHROME_CDP_PORT || daemonPort + 2);
const token = process.env.BMD_REAL_CHROME_TOKEN || `real-chrome-e2e-${runId}`;
const runtimeRoot = process.env.BMD_REAL_CHROME_RUNTIME_ROOT || `/tmp/browser-memory-real-chrome-e2e-${runId}`;
const windowsWorkRoot = process.env.BMD_REAL_CHROME_WINDOWS_WORK_ROOT || `/mnt/c/tmp/browser-memory-real-chrome-e2e-${runId}`;
const profileRoot = process.env.BMD_REAL_CHROME_PROFILE || path.join(windowsWorkRoot, 'profile');
const extensionWorkRoot = process.env.BMD_REAL_CHROME_EXTENSION_ROOT || path.join(windowsWorkRoot, 'extension-dist');
const removeProfileRoot = !process.env.BMD_REAL_CHROME_PROFILE;
const removeExtensionWorkRoot = !process.env.BMD_REAL_CHROME_EXTENSION_ROOT;
const keepArtifacts = process.env.BMD_KEEP_REAL_CHROME_E2E === '1';
const policyMode = (process.env.BMD_REAL_CHROME_POLICY_MODE || 'all').toLowerCase();
if (!['all', 'recall', 'balanced', 'strict'].includes(policyMode)) fail(`invalid BMD_REAL_CHROME_POLICY_MODE=${policyMode}`);
const allMode = policyMode === 'all';
const pythonBin = process.env.BMD_PYTHON || 'python3';

const visibleNeedle = `BMD_REAL_CHROME_VISIBLE_${runId.replace(/[^A-Za-z0-9]/g, '_')}`;
const hiddenNeedle = `BMD_REAL_CHROME_HIDDEN_${runId.replace(/[^A-Za-z0-9]/g, '_')}`;
const blockedNeedle = `BMD_REAL_CHROME_BLOCKED_${runId.replace(/[^A-Za-z0-9]/g, '_')}`;
const explicitBlockNeedle = `BMD_REAL_CHROME_EXPLICIT_BLOCK_${runId.replace(/[^A-Za-z0-9]/g, '_')}`;
const pausedNeedle = `BMD_REAL_CHROME_PAUSED_${runId.replace(/[^A-Za-z0-9]/g, '_')}`;
const localNeedle = `BMD_REAL_CHROME_LOCAL_${runId.replace(/[^A-Za-z0-9]/g, '_')}`;
const spaNeedle = `BMD_REAL_CHROME_SPA_${runId.replace(/[^A-Za-z0-9]/g, '_')}`;
const blobVideoNeedle = `BMD_REAL_CHROME_BLOB_VIDEO_${runId.replace(/[^A-Za-z0-9]/g, '_')}`;

const mediaImageUrl = `http://bmd-allowed.test:${pagePort}/media-image.png`;
const cookieMediaUrl = `http://bmd-allowed.test:${pagePort}/cookie-media.png`;
const allowedUrl = `http://bmd-allowed.test:${pagePort}/allowed`;
const blobVideoUrl = `http://bmd-allowed.test:${pagePort}/blob-video`;
const spaUrl = `http://bmd-allowed.test:${pagePort}/spa`;
const blockedUrl = `http://bank.example.test:${pagePort}/blocked`;
const explicitBlockedUrl = `http://bmd-allowed.test:${pagePort}/explicit-blocked`;
const pausedUrl = `http://bmd-allowed.test:${pagePort}/paused`;
const localUrl = `http://127.0.0.1:${pagePort}/local`;
const daemonUrl = `http://127.0.0.1:${daemonPort}`;
const cdpUrl = `http://127.0.0.1:${cdpPort}`;

let daemonProcess;
let chromeProcess;
let pageServer;
let browserCdp;
let extensionLoadPathWin;
let cookieMediaRequests = 0;

function log(message) {
  console.log(`[real-chrome-e2e] ${message}`);
}

function fail(message) {
  throw new Error(message);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function rmWithRetry(target, options) {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    try {
      await rm(target, options);
      return;
    } catch (error) {
      const retryable = ['EACCES', 'EPERM', 'ENOTEMPTY', 'EBUSY'].includes(error?.code);
      if (!retryable || attempt === 5) throw error;
      await sleep(250 * (attempt + 1));
    }
  }
}

async function pathExists(p) {
  try {
    await access(p, fsConstants.X_OK);
    return true;
  } catch (_) {
    return false;
  }
}

async function findChrome() {
  if (process.env.BMD_CHROME_EXE) {
    if (await pathExists(process.env.BMD_CHROME_EXE)) return process.env.BMD_CHROME_EXE;
    fail(`BMD_CHROME_EXE does not exist or is not executable: ${process.env.BMD_CHROME_EXE}`);
  }
  return ensureChromeForTesting();
}

async function ensureChromeForTesting() {
  const windowsUser = process.env.BMD_WINDOWS_USER || process.env.USERNAME || process.env.USER || 'Default';
  const cacheRoot = process.env.BMD_CHROME_FOR_TESTING_CACHE || `/mnt/c/Users/${windowsUser}/AppData/Local/browser-memory-daemon/chrome-for-testing`;
  const metaUrl = 'https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json';
  await mkdir(cacheRoot, { recursive: true });
  const metadataResponse = await fetch(metaUrl);
  if (!metadataResponse.ok) fail(`failed to fetch Chrome for Testing metadata: ${metadataResponse.status}`);
  const metadata = await metadataResponse.json();
  const stable = metadata.channels?.Stable;
  const win64 = stable?.downloads?.chrome?.find((item) => item.platform === 'win64');
  if (!stable?.version || !win64?.url) fail(`Chrome for Testing metadata missing Stable win64 download: ${JSON.stringify(stable)}`);
  const versionRoot = path.join(cacheRoot, stable.version);
  const exe = path.join(versionRoot, 'chrome-win64', 'chrome.exe');
  if (await pathExists(exe)) {
    log(`using cached Chrome for Testing ${stable.version}: ${exe}`);
    return exe;
  }
  if (process.env.BMD_REAL_CHROME_ALLOW_DOWNLOAD === '0') {
    fail(`Chrome for Testing ${stable.version} is not cached at ${exe}; set BMD_REAL_CHROME_ALLOW_DOWNLOAD=1 or BMD_CHROME_EXE`);
  }
  await mkdir(versionRoot, { recursive: true });
  const zipPath = path.join(versionRoot, 'chrome-win64.zip');
  log(`downloading Chrome for Testing ${stable.version} win64`);
  let result = spawnSync('curl', ['-L', '--fail', '--retry', '3', '-o', zipPath, win64.url], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  if (result.status !== 0) fail(`curl Chrome for Testing failed: ${result.stderr || result.stdout}`);
  result = spawnSync('unzip', ['-q', '-o', zipPath, '-d', versionRoot], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  if (result.status !== 0) fail(`unzip Chrome for Testing failed: ${result.stderr || result.stdout}`);
  if (!(await pathExists(exe))) fail(`Chrome for Testing unzip did not create ${exe}`);
  log(`installed Chrome for Testing ${stable.version}: ${exe}`);
  return exe;
}

function wslpathWin(wslPath) {
  const result = spawnSync('wslpath', ['-w', wslPath], { encoding: 'utf8' });
  if (result.status !== 0) {
    fail(`wslpath failed for ${wslPath}: ${result.stderr || result.stdout}`);
  }
  return result.stdout.trim();
}

async function waitForHttpJson(url, options = {}) {
  const timeoutMs = options.timeoutMs || 15000;
  const headers = options.headers || {};
  const started = Date.now();
  let lastError = '';
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url, { headers });
      if (response.ok) return await response.json();
      lastError = `${response.status} ${await response.text()}`;
    } catch (error) {
      lastError = String(error.message || error);
    }
    await sleep(250);
  }
  fail(`timed out waiting for ${url}: ${lastError}`);
}

async function daemonSearch(query) {
  const response = await fetch(`${daemonUrl}/search?q=${encodeURIComponent(query)}&limit=10`, {
    headers: { authorization: `Bearer ${token}` }
  });
  const body = await response.json();
  if (!response.ok) fail(`daemon search failed ${response.status}: ${JSON.stringify(body)}`);
  return body.results || [];
}

async function daemonPost(pathname, body) {
  const response = await fetch(`${daemonUrl}${pathname}`, {
    method: 'POST',
    headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    body: JSON.stringify(body)
  });
  const payload = await response.json();
  if (!response.ok) fail(`daemon POST ${pathname} failed ${response.status}: ${JSON.stringify(payload)}`);
  return payload;
}

async function waitForSearchHit(query, timeoutMs = 15000) {
  const started = Date.now();
  let results = [];
  while (Date.now() - started < timeoutMs) {
    results = await daemonSearch(query);
    if (results.length > 0) return results;
    await sleep(500);
  }
  fail(`search did not find expected query ${query}; last result count=${results.length}`);
}

async function assertSearchAbsent(query, label, settleMs = 2000) {
  await sleep(settleMs);
  const results = await daemonSearch(query);
  if (results.length !== 0) fail(`${label} unexpectedly became searchable: ${JSON.stringify(results)}`);
}

function startPageServer() {
  pageServer = createServer((req, res) => {
    const url = new URL(req.url || '/', `http://${req.headers.host || 'bmd-allowed.test'}`);
    const origin = String(req.headers.origin || '');
    if (origin) {
      res.setHeader('Access-Control-Allow-Origin', origin);
      res.setHeader('Access-Control-Allow-Credentials', 'true');
      res.setHeader('Vary', 'Origin');
    }
    if (req.method === 'OPTIONS') {
      res.statusCode = 204;
      res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'content-type');
      res.end();
      return;
    }
    if (url.pathname === '/media-image.png' || url.pathname === '/cookie-media.png') {
      const png = Buffer.from('iVBORw0KGgo=', 'base64');
      if (url.pathname === '/cookie-media.png') cookieMediaRequests += 1;
      if (url.pathname === '/cookie-media.png' && !String(req.headers.cookie || '').includes('bmd_media_cookie=ok')) {
        res.statusCode = 403;
        res.end('missing media cookie');
        return;
      }
      res.setHeader('content-type', 'image/png');
      res.setHeader('cache-control', 'no-store');
      res.setHeader('content-length', String(png.length));
      res.end(png);
      return;
    }
    res.setHeader('content-type', 'text/html; charset=utf-8');
    if (url.pathname === '/allowed') {
      // No SameSite attribute: the synthetic profile disables modern SameSite hardening
      // so this exercises credentialed extension fetch without requiring HTTPS.
      res.setHeader('Set-Cookie', 'bmd_media_cookie=ok; Path=/');
      res.end(`<!doctype html>
<html>
  <head><title>Allowed Real Chrome E2E</title></head>
  <body>
    <main>
      <h1>Allowed capture fixture</h1>
      <p>Visible capture proof ${visibleNeedle} from a real Windows Chrome extension.</p>
      <img src="/media-image.png" width="64" height="64" alt="Synthetic public media artifact">
      <img src="/cookie-media.png" width="64" height="64" alt="Synthetic cookie media artifact">
      <p style="display:none">Hidden text must not be captured ${hiddenNeedle}</p>
      <p aria-hidden="true">ARIA hidden text must not be captured ${hiddenNeedle}_ARIA</p>
      <input value="Input field must not be captured ${hiddenNeedle}_INPUT">
      <textarea>Textarea must not be captured ${hiddenNeedle}_TEXTAREA</textarea>
      <div contenteditable="true">Editable text must not be captured ${hiddenNeedle}_EDITABLE</div>
    </main>
  </body>
</html>`);
      return;
    }
    if (url.pathname === '/explicit-blocked') {
      res.end(`<!doctype html><title>Explicit block fixture</title><body>Explicit policy block proof ${explicitBlockNeedle}</body>`);
      return;
    }
    if (url.pathname === '/paused') {
      res.end(`<!doctype html><title>Paused capture fixture</title><body>Paused capture proof ${pausedNeedle}</body>`);
      return;
    }
    if (url.pathname === '/spa' || url.pathname === '/spa/route-two') {
      res.end(`<!doctype html>
<html>
  <head><title>Delayed SPA fixture</title></head>
  <body>
    <main>
      <p id="spa-content">Loading</p>
    </main>
    <script>
      setTimeout(() => {
        history.pushState({}, '', '/spa/route-two');
        document.getElementById('spa-content').textContent = 'Delayed SPA route proof ${spaNeedle} after history.pushState.';
      }, 500);
    </script>
  </body>
</html>`);
      return;
    }
    if (url.pathname === '/blob-video') {
      res.end(`<!doctype html>
<html>
  <head><title>Blob Video Fixture</title></head>
  <body>
    <main>
      <p>Blob video capture proof ${blobVideoNeedle} from a real Windows Chrome extension.</p>
      <video id="blob-video" width="160" height="90" muted playsinline title="Synthetic blob video"></video>
    </main>
    <script>
      const bytes = new Uint8Array([0,0,0,24,102,116,121,112,105,115,111,109,0,0,2,0,105,115,111,109,105,115,111,50,97,118,99,49,109,112,52,49]);
      const blob = new Blob([bytes], {type: 'video/mp4'});
      document.getElementById('blob-video').src = URL.createObjectURL(blob);
    </script>
  </body>
</html>`);
      return;
    }
    if (url.pathname === '/blocked') {
      res.end(`<!doctype html><title>Blocked banking fixture</title><body>Blocked banking proof ${blockedNeedle}</body>`);
      return;
    }
    if (url.pathname === '/local') {
      res.end(`<!doctype html><title>Localhost fixture</title><body>Localhost private proof ${localNeedle}</body>`);
      return;
    }
    res.statusCode = 404;
    res.end('not found');
  });

  return new Promise((resolve, reject) => {
    pageServer.once('error', reject);
    pageServer.listen(pagePort, '127.0.0.1', () => {
      pageServer.off('error', reject);
      log(`fixture HTTP server listening on http://127.0.0.1:${pagePort}`);
      resolve();
    });
  });
}

async function startDaemon() {
  await mkdir(runtimeRoot, { recursive: true });
  const env = {
    ...process.env,
    PYTHONPATH: path.join(ROOT, 'daemon/src'),
    BMD_API_TOKEN: token,
    BMD_RUNTIME_ROOT: runtimeRoot,
    BMD_PORT: String(daemonPort),
    BMD_HOST: '127.0.0.1',
    BMD_POLICY_MODE: policyMode
  };
  daemonProcess = spawn(pythonBin, [
    '-m', 'browser_memory_daemon',
    '--host', '127.0.0.1',
    '--port', String(daemonPort),
    '--token', token,
    '--runtime-root', runtimeRoot,
    '--policy-mode', policyMode,
    'serve'
  ], { cwd: ROOT, env, stdio: ['ignore', 'pipe', 'pipe'] });

  daemonProcess.stdout.on('data', (chunk) => process.stdout.write(`[daemon] ${chunk}`));
  daemonProcess.stderr.on('data', (chunk) => process.stderr.write(`[daemon:stderr] ${chunk}`));
  daemonProcess.once('exit', (code, signal) => {
    if (code !== null && code !== 0 && code !== 130) {
      process.stderr.write(`[daemon] exited code=${code} signal=${signal}\n`);
    }
  });

  const health = await waitForHttpJson(`${daemonUrl}/health`, { timeoutMs: 15000 });
  if (!health.ok) fail(`daemon health did not report ok: ${JSON.stringify(health)}`);
  await waitForHttpJson(`${daemonUrl}/ready`, {
    timeoutMs: 15000,
    headers: { authorization: `Bearer ${token}` }
  });
  log(`daemon ready at ${daemonUrl}; runtimeRoot=${runtimeRoot}`);
}

async function prepareExtensionDist() {
  const extDist = path.join(ROOT, 'extension/dist');
  await rm(extensionWorkRoot, { recursive: true, force: true });
  await mkdir(path.dirname(extensionWorkRoot), { recursive: true });
  await cp(extDist, extensionWorkRoot, { recursive: true });
  return extensionWorkRoot;
}

async function startChrome() {
  const chrome = await findChrome();
  const extDist = await prepareExtensionDist();
  const extWin = wslpathWin(extDist);
  extensionLoadPathWin = extWin;
  const profileWin = wslpathWin(profileRoot);
  await mkdir(profileRoot, { recursive: true });

  const args = [
    `--user-data-dir=${profileWin}`,
    `--remote-debugging-port=${cdpPort}`,
    '--remote-debugging-address=127.0.0.1',
    '--no-sandbox',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-sync',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-features=SameSiteByDefaultCookies,CookiesWithoutSameSiteMustBeSecure,ThirdPartyStoragePartitioning,ThirdPartyCookiesPhaseout,TrackingProtection3pcd',
    `--unsafely-treat-insecure-origin-as-secure=http://bmd-allowed.test:${pagePort}`,
    `--host-resolver-rules=MAP bmd-allowed.test 127.0.0.1,MAP bank.example.test 127.0.0.1,EXCLUDE localhost`,
    `--load-extension=${extWin}`,
    'about:blank'
  ];
  if (process.env.BMD_REAL_CHROME_HEADLESS === '1') {
    args.splice(3, 0, '--headless=new');
  }

  chromeProcess = spawn(chrome, args, { stdio: ['ignore', 'pipe', 'pipe'] });
  chromeProcess.stdout.on('data', (chunk) => process.stdout.write(`[chrome] ${chunk}`));
  chromeProcess.stderr.on('data', (chunk) => process.stderr.write(`[chrome:stderr] ${chunk}`));
  chromeProcess.once('exit', (code, signal) => {
    if (code !== null && code !== 0) {
      process.stderr.write(`[chrome] exited code=${code} signal=${signal}\n`);
    }
  });

  const version = await waitForHttpJson(`${cdpUrl}/json/version`, { timeoutMs: 20000 });
  log(`Chrome CDP ready: ${version.Browser || 'unknown browser'}`);
  return version.webSocketDebuggerUrl;
}

class CdpConnection {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
    this.events = [];
  }

  async open() {
    this.ws = new WebSocket(this.wsUrl);
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error(`CDP websocket timeout: ${this.wsUrl}`)), 10000);
      this.ws.addEventListener('open', () => {
        clearTimeout(timeout);
        resolve();
      }, { once: true });
      this.ws.addEventListener('error', (event) => {
        clearTimeout(timeout);
        reject(new Error(`CDP websocket error: ${event.message || 'unknown error'}`));
      }, { once: true });
    });
    this.ws.addEventListener('message', (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(JSON.stringify(message.error)));
        else resolve(message.result || {});
      } else {
        this.events.push(message);
        if (this.events.length > 500) this.events.shift();
      }
    });
  }

  send(method, params = {}, sessionId = undefined) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) fail('CDP websocket is not open');
    const id = this.nextId++;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    const promise = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP command timeout: ${method}`));
      }, 15000);
      this.pending.set(id, {
        resolve: (value) => {
          clearTimeout(timeout);
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timeout);
          reject(error);
        }
      });
    });
    this.ws.send(JSON.stringify(payload));
    return promise;
  }

  close() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.close();
  }
}

async function connectBrowserCdp(wsUrl) {
  const cdp = new CdpConnection(wsUrl);
  await cdp.open();
  return cdp;
}

async function getTargets(cdp) {
  const result = await cdp.send('Target.getTargets');
  return result.targetInfos || [];
}

async function waitForTarget(cdp, predicate, label, timeoutMs = 15000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const targets = await getTargets(cdp);
    const target = targets.find(predicate);
    if (target) return target;
    await sleep(250);
  }
  const targets = await getTargets(cdp);
  fail(`timed out waiting for ${label}; targets=${targets.map((t) => `${t.type}:${t.url}`).join(', ')}`);
}

async function attach(cdp, targetId) {
  const result = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  return result.sessionId;
}

async function evaluate(cdp, sessionId, expression, { awaitPromise = false } = {}) {
  const result = await cdp.send('Runtime.evaluate', {
    expression,
    awaitPromise,
    returnByValue: true
  }, sessionId);
  if (result.exceptionDetails) fail(`Runtime.evaluate exception: ${JSON.stringify(result.exceptionDetails)}`);
  return result.result?.value;
}

async function configureExtensionStorage(cdp) {
  await cdp.send('Target.setDiscoverTargets', { discover: true });
  const started = Date.now();
  let seen = [];
  while (Date.now() - started < 20000) {
    const targets = await getTargets(cdp);
    const serviceWorkers = targets.filter((target) => target.type === 'service_worker' && target.url.startsWith('chrome-extension://'));
    seen = serviceWorkers.map((target) => target.url);
    for (const serviceWorker of serviceWorkers) {
      const sessionId = await attach(cdp, serviceWorker.targetId);
      let manifestName = '';
      try {
        manifestName = await evaluate(cdp, sessionId, `chrome.runtime && chrome.runtime.getManifest ? chrome.runtime.getManifest().name : ''`);
      } catch (_) {
        continue;
      }
      if (manifestName !== 'Browser Memory Daemon') continue;
      const extensionId = new URL(serviceWorker.url).hostname;
      await evaluate(
        cdp,
        sessionId,
        `chrome.storage.local.set(${JSON.stringify({
          daemonUrl,
          apiToken: token,
          capturePaused: false,
          policyMode,
          captureQueue: [],
          visitEventQueue: [],
          tabVisitState: {}
        })}).then(() => 'ok')`,
        { awaitPromise: true }
      );
      const stored = await evaluate(
        cdp,
        sessionId,
        `chrome.storage.local.get(['daemonUrl', 'apiToken', 'capturePaused', 'policyMode', 'captureQueue', 'visitEventQueue', 'tabVisitState']).then((value) => JSON.stringify(value))`,
        { awaitPromise: true }
      );
      const parsed = JSON.parse(stored || '{}');
      if (parsed.daemonUrl !== daemonUrl || parsed.apiToken !== token || parsed.capturePaused !== false || parsed.policyMode !== policyMode) {
        fail(`extension storage verification failed: ${stored}`);
      }
      const injectionProbe = await evaluate(
        cdp,
        sessionId,
        `JSON.stringify({hasScripting: Boolean(chrome.scripting && chrome.scripting.executeScript), hasTabs: Boolean(chrome.tabs && chrome.tabs.onUpdated), hasPolicy: Boolean(globalThis.shouldBlockBrowserMemoryUrl)})`
      );
      log(`extension injection capabilities ${injectionProbe}`);
      log(`configured extension ${extensionId} storage for ${daemonUrl} policyMode=${policyMode}`);
      return { extensionId, storageSessionId: sessionId };
    }
    await sleep(250);
  }
  fail(`timed out waiting for Browser Memory Daemon service worker; seen=${seen.join(', ')}`);
}

async function openPageAndWait(cdp, url) {
  const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' });
  await cdp.send('Target.activateTarget', { targetId });
  const sessionId = await attach(cdp, targetId);
  await cdp.send('Runtime.enable', {}, sessionId);
  await cdp.send('Log.enable', {}, sessionId);
  await cdp.send('Page.enable', {}, sessionId);
  await cdp.send('Page.navigate', { url }, sessionId);
  const started = Date.now();
  while (Date.now() - started < 15000) {
    const state = await evaluate(cdp, sessionId, 'document.readyState');
    if (state === 'complete' || state === 'interactive') break;
    await sleep(250);
  }
  const title = await evaluate(cdp, sessionId, 'document.title');
  log(`opened ${url} title=${JSON.stringify(title)}`);
  await sleep(1500);
  return { targetId, sessionId, title };
}

async function triggerExtensionInjection(cdp, storageSessionId, url) {
  const result = await evaluate(
    cdp,
    storageSessionId,
    `chrome.tabs.query({url: ${JSON.stringify(url)}}).then((tabs) => tabs[0] ? maybeInjectCapture(tabs[0].id, tabs[0].url) : {ok: false, error: 'tab-not-found'}).then((value) => JSON.stringify(value))`,
    { awaitPromise: true }
  );
  log(`extension injection for ${url}: ${result}`);
  return JSON.parse(result || '{}');
}

async function getContentScriptStatus(cdp, storageSessionId, url) {
  const result = await evaluate(
    cdp,
    storageSessionId,
    `chrome.tabs.query({url: ${JSON.stringify(url)}}).then((tabs) => tabs[0] ? chrome.scripting.executeScript({target: {tabId: tabs[0].id}, func: () => ({status: globalThis.__BMD_LAST_CAPTURE_STATUS || null, bodyTextLength: document.body ? document.body.innerText.length : -1, bodyTextSample: document.body ? document.body.innerText.slice(0, 160) : '', bodyChildCount: document.body ? document.body.childNodes.length : -1})}) : [{result: {error: 'tab-not-found'}}]).then((values) => JSON.stringify(values.map((value) => value.result)))`,
    { awaitPromise: true }
  );
  return JSON.parse(result || '[]');
}

async function getQueueLengths(cdp, storageSessionId) {
  const stored = await evaluate(
    cdp,
    storageSessionId,
    `chrome.storage.local.get({captureQueue: [], visitEventQueue: []}).then((value) => JSON.stringify({captureQueue: value.captureQueue || [], visitEventQueue: value.visitEventQueue || []}))`,
    { awaitPromise: true }
  );
  const parsed = JSON.parse(stored || '{}');
  return {
    captureQueue: (parsed.captureQueue || []).length,
    visitEventQueue: (parsed.visitEventQueue || []).length
  };
}

async function waitForQueuesEmpty(cdp, storageSessionId, timeoutMs = 15000) {
  const started = Date.now();
  let lengths = { captureQueue: -1, visitEventQueue: -1 };
  while (Date.now() - started < timeoutMs) {
    lengths = await getQueueLengths(cdp, storageSessionId);
    if (lengths.captureQueue === 0 && lengths.visitEventQueue === 0) return lengths;
    await sleep(500);
  }
  return lengths;
}

async function getMediaQueueCounts(cdp, storageSessionId) {
  const stored = await evaluate(
    cdp,
    storageSessionId,
    `globalThis.BrowserMemoryMediaQueue ? BrowserMemoryMediaQueue.countMediaTasksByStatus().then((value) => JSON.stringify(value)) : JSON.stringify({unavailable: 1})`,
    { awaitPromise: true }
  );
  return JSON.parse(stored || '{}');
}

async function waitForMediaQueueEmpty(cdp, storageSessionId, timeoutMs = 20000) {
  const started = Date.now();
  let counts = {};
  while (Date.now() - started < timeoutMs) {
    counts = await getMediaQueueCounts(cdp, storageSessionId);
    const total = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
    if (total === 0) return counts;
    await evaluate(cdp, storageSessionId, `drainMediaQueue({limit: 10, budgetMs: 10000}).then((value) => JSON.stringify(value))`, { awaitPromise: true }).catch(() => null);
    await sleep(500);
  }
  return counts;
}

async function getQueueDebug(cdp, storageSessionId) {
  const stored = await evaluate(
    cdp,
    storageSessionId,
    `chrome.storage.local.get({captureQueue: [], visitEventQueue: [], lastVisitEventError: null}).then((value) => JSON.stringify({captureQueue: value.captureQueue || [], visitEventQueue: value.visitEventQueue || [], lastVisitEventError: value.lastVisitEventError || null}))`,
    { awaitPromise: true }
  );
  return JSON.parse(stored || '{}');
}

function queryDbCounts() {
  const dbPath = path.join(runtimeRoot, 'browser-memory.sqlite3');
  const script = `
import json, sqlite3, sys
conn = sqlite3.connect(${JSON.stringify(dbPath)})
counts = {}
for table in ['documents', 'visits', 'visit_events', 'capture_observations', 'snapshots', 'chunks', 'media_artifacts', 'media_fetch_tasks', 'audit_events']:
    counts[table] = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
counts['browser_identity_observations'] = conn.execute("SELECT COUNT(*) FROM capture_observations WHERE idempotency_key LIKE 'browser:%' AND navigation_id IS NOT NULL AND TRIM(navigation_id) != ''").fetchone()[0]
counts['sqlite_authoritative_snapshots'] = conn.execute("SELECT COUNT(*) FROM snapshots WHERE cleaned_text IS NOT NULL AND cleaned_text_source = 'capture'").fetchone()[0]
counts['audit_event_types'] = dict(conn.execute('SELECT event_type, COUNT(*) FROM audit_events GROUP BY event_type').fetchall())
print(json.dumps(counts, sort_keys=True))
`;
  const result = spawnSync(pythonBin, ['-c', script], { encoding: 'utf8' });
  if (result.status !== 0) fail(`DB count query failed: ${result.stderr || result.stdout}`);
  return JSON.parse(result.stdout.trim());
}

function queryDbMediaState() {
  const dbPath = path.join(runtimeRoot, 'browser-memory.sqlite3');
  const script = `
import json, pathlib, sqlite3
conn = sqlite3.connect(${JSON.stringify(dbPath)})
conn.row_factory = sqlite3.Row
rows = [dict(row) for row in conn.execute('SELECT id, media_type, role, source_url, mime_type, byte_size, file_path, blob_locator, storage_tier, spool_locator, capture_status FROM media_artifacts ORDER BY created_at ASC').fetchall()]
tasks = dict(conn.execute('SELECT status, COUNT(*) FROM media_fetch_tasks GROUP BY status').fetchall())
for row in rows:
    path = pathlib.Path(row['file_path']) if row.get('file_path') else None
    row['has_file'] = bool(path and path.exists())
    row['file_size'] = path.stat().st_size if path and path.exists() else 0
    locator = pathlib.PurePosixPath(row['blob_locator']) if row.get('blob_locator') else None
    row['locator_is_relative'] = bool(row.get('storage_tier') == 'media-root' and locator and not locator.is_absolute() and '..' not in locator.parts)
print(json.dumps({'rows': rows, 'stored': sum(1 for row in rows if row.get('has_file')), 'bytes': sum(row.get('file_size', 0) for row in rows), 'tasks': tasks}, sort_keys=True))
`;
  const result = spawnSync(pythonBin, ['-c', script], { encoding: 'utf8' });
  if (result.status !== 0) fail(`DB media query failed: ${result.stderr || result.stdout}`);
  return JSON.parse(result.stdout.trim());
}

async function waitForMediaArtifactStored(timeoutMs = 20000) {
  const started = Date.now();
  let media = { rows: [], stored: 0, bytes: 0, tasks: {} };
  while (Date.now() - started < timeoutMs) {
    media = queryDbMediaState();
    const storedRows = media.rows.filter((row) => row.has_file);
    if (media.stored >= 2 && media.bytes >= 16 && storedRows.every((row) => row.locator_is_relative)) return media;
    await sleep(500);
  }
  fail(`timed out waiting for stored media artifacts: ${JSON.stringify(media)}`);
}

async function waitForBlobVideoStored(timeoutMs = 20000) {
  const started = Date.now();
  let media = { rows: [], stored: 0, bytes: 0, tasks: {} };
  while (Date.now() - started < timeoutMs) {
    media = queryDbMediaState();
    const row = media.rows.find((item) => item.media_type === 'video' && String(item.source_url || '').startsWith('blob:') && item.has_file && item.locator_is_relative && Number(item.file_size || 0) >= 16);
    if (row) return { media, row };
    await sleep(500);
  }
  fail(`timed out waiting for stored blob video artifact: ${JSON.stringify(media)}`);
}

function queryVisitTelemetry() {
  const dbPath = path.join(runtimeRoot, 'browser-memory.sqlite3');
  const script = `
import json, sqlite3
conn = sqlite3.connect(${JSON.stringify(dbPath)})
conn.row_factory = sqlite3.Row
visits = [dict(row) for row in conn.execute('SELECT id, url, dwell_seconds FROM visits ORDER BY captured_at ASC').fetchall()]
events = [dict(row) for row in conn.execute('SELECT visit_id, url, event_type, active_seconds, max_scroll_percent FROM visit_events ORDER BY created_at ASC').fetchall()]
print(json.dumps({'visits': visits, 'events': events}, sort_keys=True))
`;
  const result = spawnSync(pythonBin, ['-c', script], { encoding: 'utf8' });
  if (result.status !== 0) fail(`DB telemetry query failed: ${result.stderr || result.stdout}`);
  return JSON.parse(result.stdout.trim());
}

async function waitForVisitTelemetry(predicate, label, timeoutMs = 15000) {
  const started = Date.now();
  let telemetry = { visits: [], events: [] };
  while (Date.now() - started < timeoutMs) {
    telemetry = queryVisitTelemetry();
    if (predicate(telemetry)) return telemetry;
    await sleep(500);
  }
  fail(`timed out waiting for visit telemetry ${label}: ${JSON.stringify(telemetry)}`);
}

async function runScenario() {
  await startPageServer();
  await startDaemon();
  const wsUrl = await startChrome();
  browserCdp = await connectBrowserCdp(wsUrl);
  const { storageSessionId } = await configureExtensionStorage(browserCdp);
  await sleep(1000);

  await evaluate(
    browserCdp,
    storageSessionId,
    `chrome.storage.local.set({capturePaused: true}).then(() => 'ok')`,
    { awaitPromise: true }
  );
  await openPageAndWait(browserCdp, pausedUrl);
  const pausedInjection = await triggerExtensionInjection(browserCdp, storageSessionId, pausedUrl);
  if (!pausedInjection.skipped || pausedInjection.reason !== 'paused') {
    fail(`paused capture control did not skip injection: ${JSON.stringify(pausedInjection)}`);
  }
  await assertSearchAbsent(pausedNeedle, 'paused capture fixture');
  await evaluate(
    browserCdp,
    storageSessionId,
    `chrome.storage.local.set({capturePaused: false}).then(() => 'ok')`,
    { awaitPromise: true }
  );
  log('pause/resume control skipped capture without storing the paused fixture');

  const explicitRule = await daemonPost('/policy/rules', { rule_type: 'url-prefix', pattern: explicitBlockedUrl, action: 'block' });
  log(`created explicit URL-prefix block rule ${explicitRule.rule?.id || explicitRule.id || 'unknown'}`);
  await openPageAndWait(browserCdp, explicitBlockedUrl);
  await triggerExtensionInjection(browserCdp, storageSessionId, explicitBlockedUrl);
  await assertSearchAbsent(explicitBlockNeedle, 'explicit policy block fixture');
  log('explicit URL-prefix block rule prevented storage in real Chrome e2e');

  await openPageAndWait(browserCdp, allowedUrl);
  await triggerExtensionInjection(browserCdp, storageSessionId, allowedUrl);
  let visibleResults;
  try {
    visibleResults = await waitForSearchHit(visibleNeedle);
  } catch (error) {
    const queueLengths = await getQueueLengths(browserCdp, storageSessionId).catch((queueError) => `queue-error:${queueError.message || queueError}`);
    const storageDump = await evaluate(
      browserCdp,
      storageSessionId,
      `Promise.all([chrome.storage.local.get(null), chrome.permissions.contains({origins: ['http://bmd-allowed.test/*']}), chrome.tabs.query({})]).then(([storage, hasOrigin, tabs]) => JSON.stringify({storage, hasOrigin, tabs: tabs.map((tab) => ({id: tab.id, url: tab.url, status: tab.status}))}))`,
      { awaitPromise: true }
    ).catch((storageError) => `storage-error:${storageError.message || storageError}`);
    const targets = await getTargets(browserCdp).catch(() => []);
    const contentStatus = await getContentScriptStatus(browserCdp, storageSessionId, allowedUrl).catch((statusError) => `status-error:${statusError.message || statusError}`);
    const recentEvents = (browserCdp.events || []).slice(-30).map((event) => ({ sessionId: event.sessionId, method: event.method, params: event.params })).filter((event) => ['Runtime.exceptionThrown', 'Log.entryAdded', 'Runtime.consoleAPICalled'].includes(event.method));
    const counts = queryDbCounts();
    fail(`${error.message}; queueLengths=${JSON.stringify(queueLengths)}; contentStatus=${JSON.stringify(contentStatus)}; storage=${storageDump}; dbCounts=${JSON.stringify(counts)}; events=${JSON.stringify(recentEvents).slice(0, 2000)}; targets=${targets.map((target) => `${target.type}:${target.url}`).join(', ')}`);
  }
  log(`allowed page search hit count=${visibleResults.length}`);
  const drainResult = await evaluate(browserCdp, storageSessionId, `drainMediaQueue({limit: 10, budgetMs: 15000}).then((value) => JSON.stringify(value))`, { awaitPromise: true });
  log(`browser lazy media drain ${drainResult}`);
  const mediaState = await waitForMediaArtifactStored();
  if (cookieMediaRequests < 2) fail(`cookie media sidecar fetch was not proven; request count=${cookieMediaRequests}`);
  log(`allowed page media artifact stored count=${mediaState.stored} bytes=${mediaState.bytes} cookieRequests=${cookieMediaRequests}`);

  await openPageAndWait(browserCdp, blobVideoUrl);
  await triggerExtensionInjection(browserCdp, storageSessionId, blobVideoUrl);
  const blobVideoResults = await waitForSearchHit(blobVideoNeedle, 20000);
  const blobVideoState = await waitForBlobVideoStored();
  log(`blob video stored artifact=${blobVideoState.row.id} bytes=${blobVideoState.row.file_size}`);

  const hiddenResults = await daemonSearch(hiddenNeedle);
  if (hiddenResults.length !== 0) fail(`hidden/editable/form text leaked into search: ${JSON.stringify(hiddenResults)}`);
  log('hidden/form/editable text absent from search');

  const spaPage = await openPageAndWait(browserCdp, spaUrl);
  const spaCurrentUrl = await evaluate(browserCdp, spaPage.sessionId, 'location.href');
  await triggerExtensionInjection(browserCdp, storageSessionId, spaCurrentUrl);
  const spaResults = await waitForSearchHit(spaNeedle, 20000);
  if (!spaResults[0].url.endsWith('/spa/route-two')) fail(`SPA route capture used wrong URL: ${JSON.stringify(spaResults[0])}`);
  log(`delayed SPA route capture hit count=${spaResults.length}`);

  await openPageAndWait(browserCdp, blockedUrl);
  await triggerExtensionInjection(browserCdp, storageSessionId, blockedUrl);
  await sleep(2000);
  const blockedResults = allMode ? await waitForSearchHit(blockedNeedle) : await daemonSearch(blockedNeedle);
  if (allMode) {
    log(`all mode stored sensitive-domain fixture hit count=${blockedResults.length}`);
  } else {
    if (blockedResults.length !== 0) fail(`sensitive-domain page was stored: ${JSON.stringify(blockedResults)}`);
    log('sensitive-domain page absent from search');
  }

  await openPageAndWait(browserCdp, localUrl);
  await triggerExtensionInjection(browserCdp, storageSessionId, localUrl);
  await sleep(2000);
  const localResults = allMode ? await waitForSearchHit(localNeedle) : await daemonSearch(localNeedle);
  if (allMode) {
    log(`all mode stored localhost/private fixture hit count=${localResults.length}`);
  } else {
    if (localResults.length !== 0) fail(`localhost/private page was stored: ${JSON.stringify(localResults)}`);
    log('localhost/private page absent from search');
  }

  const telemetry = await waitForVisitTelemetry(
    (state) => state.events.length >= 1 && state.visits.some((visit) => visit.url === allowedUrl && Number(visit.dwell_seconds || 0) >= 1),
    'allowed tab dwell event'
  );
  const allowedVisit = telemetry.visits.find((visit) => visit.url === allowedUrl);
  const allowedEvent = telemetry.events.find((event) => event.url === allowedUrl);
  if (!allowedEvent || !['tab-deactivated', 'navigation-away', 'tab-closed', 'window-blurred'].includes(allowedEvent.event_type)) {
    fail(`missing expected lifecycle event for allowed page: ${JSON.stringify(telemetry)}`);
  }
  if (Number(allowedEvent.max_scroll_percent || 0) < 0 || Number(allowedEvent.max_scroll_percent || 0) > 100) {
    fail(`invalid scroll percent in lifecycle event: ${JSON.stringify(allowedEvent)}`);
  }
  log(`visit lifecycle telemetry recorded dwell=${allowedVisit.dwell_seconds}s event=${allowedEvent.event_type}`);

  const queueLengths = await waitForQueuesEmpty(browserCdp, storageSessionId);
  const mediaQueueCounts = await waitForMediaQueueEmpty(browserCdp, storageSessionId);
  const mediaQueueTotal = Object.values(mediaQueueCounts).reduce((sum, value) => sum + Number(value || 0), 0);
  if (queueLengths.captureQueue !== 0 || queueLengths.visitEventQueue !== 0 || mediaQueueTotal !== 0) {
    const queueDebug = await getQueueDebug(browserCdp, storageSessionId);
    fail(`extension queues not drained/empty: ${JSON.stringify({ ...queueLengths, mediaQueueCounts })} debug=${JSON.stringify(queueDebug).slice(0, 2000)}`);
  }
  log('extension capture, lifecycle, and media queues are empty');

  const counts = queryDbCounts();
  const expectedDocuments = allMode ? 6 : 3;
  const expectedSnapshots = allMode ? 6 : 3;
  if (counts.documents !== expectedDocuments || counts.snapshots !== expectedSnapshots || counts.sqlite_authoritative_snapshots !== expectedSnapshots || counts.chunks < expectedSnapshots || counts.visit_events < 1 || counts.browser_identity_observations < expectedSnapshots) {
    fail(`unexpected DB counts after policy-mode scenarios: ${JSON.stringify({ policyMode, counts, expectedDocuments, expectedSnapshots })}`);
  }
  log(`DB counts ${JSON.stringify(counts)}`);

  console.log(JSON.stringify({
    ok: true,
    policyMode,
    daemonUrl,
    allowedUrl,
    blobVideoUrl,
    spaUrl,
    blockedUrl,
    explicitBlockedUrl,
    pausedUrl,
    localUrl,
    visibleNeedle,
    blobVideoNeedle,
    hiddenNeedle,
    explicitBlockNeedle,
    pausedNeedle,
    spaNeedle,
    blockedNeedle,
    localNeedle,
    runtimeRoot,
    profileRoot,
    extensionWorkRoot,
    windowsWorkRoot,
    counts,
    mediaState,
    blobVideoState,
    mediaQueueCounts,
    telemetry,
    visibleResult: visibleResults[0],
    blobVideoResult: blobVideoResults[0]
  }, null, 2));
}

async function cleanup() {
  if (browserCdp) {
    try { await browserCdp.send('Browser.close'); } catch (_) {}
    browserCdp.close();
  }
  if (chromeProcess && !chromeProcess.killed) {
    try { chromeProcess.kill(); } catch (_) {}
  }
  if (daemonProcess && !daemonProcess.killed) {
    try { daemonProcess.kill('SIGTERM'); } catch (_) {}
  }
  if (pageServer) {
    await new Promise((resolve) => pageServer.close(resolve));
  }
  await sleep(300);
  if (!keepArtifacts) {
    if (removeProfileRoot) await rmWithRetry(profileRoot, { recursive: true, force: true });
    if (removeExtensionWorkRoot) await rmWithRetry(extensionWorkRoot, { recursive: true, force: true });
    if (!process.env.BMD_REAL_CHROME_WINDOWS_WORK_ROOT) await rmWithRetry(windowsWorkRoot, { recursive: true, force: true });
    await rmWithRetry(runtimeRoot, { recursive: true, force: true });
  } else {
    log(`kept artifacts: runtimeRoot=${runtimeRoot} profileRoot=${profileRoot} extensionWorkRoot=${extensionWorkRoot}`);
  }
}

try {
  await runScenario();
} finally {
  await cleanup();
}
