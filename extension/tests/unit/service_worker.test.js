const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const { MemoryMediaQueueStore } = require('../../src/media_queue.js');
const { normalizeDaemonUrl, authHeaders } = require('../../src/shared.js');
const { shouldBlockUrl, normalizePolicyMode } = require('../../src/extractor.js');

const SERVICE_WORKER = fs.readFileSync(path.resolve(__dirname, '../../src/service_worker.js'), 'utf8');

function jsonResponse(status, body = {}, { headers = {}, arrayBuffer = null, blob = null } = {}) {
  const lowerHeaders = new Map(Object.entries(headers).map(([key, value]) => [String(key).toLowerCase(), String(value)]));
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    headers: {
      get(name) {
        return lowerHeaders.get(String(name).toLowerCase()) || '';
      }
    },
    async json() {
      return body;
    },
    async arrayBuffer() {
      if (arrayBuffer) return arrayBuffer;
      if (blob && typeof blob.arrayBuffer === 'function') return blob.arrayBuffer();
      return new ArrayBuffer(0);
    },
    async blob() {
      if (blob) return blob;
      return new Blob([arrayBuffer || new Uint8Array()], { type: lowerHeaders.get('content-type') || '' });
    }
  };
}

function cloneDefaults(defaults, storage) {
  if (defaults === undefined || defaults === null) return { ...storage };
  if (typeof defaults === 'string') return { [defaults]: storage[defaults] };
  if (Array.isArray(defaults)) {
    return defaults.reduce((acc, key) => {
      acc[key] = storage[key];
      return acc;
    }, {});
  }
  if (typeof defaults === 'object') return { ...defaults, ...storage };
  return {};
}

function createChromeMock(storage, calls) {
  const listeners = {
    messages: [],
    startup: [],
    installed: [],
    alarms: [],
    tabUpdated: [],
    tabActivated: [],
    tabRemoved: [],
    windowFocusChanged: [],
    debuggerEvents: [],
    debuggerDetach: []
  };
  return {
    runtime: {
      lastError: null,
      onMessage: { addListener(listener) { listeners.messages.push(listener); } },
      onStartup: { addListener(listener) { listeners.startup.push(listener); } },
      onInstalled: { addListener(listener) { listeners.installed.push(listener); } }
    },
    storage: {
      local: {
        async get(defaults) {
          return cloneDefaults(defaults, storage);
        },
        async set(values) {
          calls.storageSets.push(values);
          Object.assign(storage, values);
        },
        async remove(keys) {
          for (const key of Array.isArray(keys) ? keys : [keys]) delete storage[key];
        }
      }
    },
    tabs: {
      onUpdated: { addListener(listener) { listeners.tabUpdated.push(listener); } },
      onActivated: { addListener(listener) { listeners.tabActivated.push(listener); } },
      onRemoved: { addListener(listener) { listeners.tabRemoved.push(listener); } },
      query(_query, callback) { callback([]); },
      get(tabId, callback) { callback({ id: tabId, url: 'https://example.test/', active: true }); },
      create(details) { calls.createdTabs.push(details); return Promise.resolve({ id: 99, ...details }); }
    },
    windows: {
      WINDOW_ID_NONE: -1,
      onFocusChanged: { addListener(listener) { listeners.windowFocusChanged.push(listener); } }
    },
    scripting: {
      async executeScript(details) {
        calls.scripts.push(details);
        return [];
      }
    },
    alarms: {
      create(name, details) { calls.alarms.push({ name, details }); },
      onAlarm: { addListener(listener) { listeners.alarms.push(listener); } }
    },
    debugger: {
      attach(_target, _version, callback) { callback && callback(); },
      detach(_target, callback) { callback && callback(); },
      sendCommand(_target, _method, _params, callback) { callback && callback({}); },
      onEvent: { addListener(listener) { listeners.debuggerEvents.push(listener); } },
      onDetach: { addListener(listener) { listeners.debuggerDetach.push(listener); } }
    },
    __listeners: listeners
  };
}

function createServiceWorkerHarness({ storage = {}, fetchImpl, mediaQueue = new MemoryMediaQueueStore() } = {}) {
  const calls = { fetches: [], scripts: [], alarms: [], storageSets: [], createdTabs: [], timers: [] };
  const chrome = createChromeMock(storage, calls);
  const context = {
    console,
    URL,
    Date,
    Math,
    Number,
    String,
    Boolean,
    Array,
    Object,
    Map,
    Set,
    Promise,
    JSON,
    Error,
    RegExp,
    encodeURIComponent,
    decodeURIComponent,
    Blob,
    crypto: { randomUUID: () => `uuid-${calls.storageSets.length}-${calls.fetches.length}` },
    setTimeout(fn) {
      calls.timers.push(fn);
      return calls.timers.length;
    },
    clearTimeout() {},
    importScripts() {},
    normalizeDaemonUrl,
    authHeaders,
    shouldBlockBrowserMemoryUrl: shouldBlockUrl,
    normalizeBrowserMemoryPolicyMode: normalizePolicyMode,
    BrowserMemoryMediaQueue: mediaQueue,
    BrowserMemoryCdpRecorder: null,
    chrome,
    fetch: async (url, init = {}) => {
      calls.fetches.push({ url: String(url), init });
      if (!fetchImpl) throw new Error(`unexpected fetch ${url}`);
      return fetchImpl(String(url), init, { calls, storage, mediaQueue });
    }
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(SERVICE_WORKER, context, { filename: 'service_worker.js' });

  async function sendMessage(message, sender = {}) {
    assert.equal(chrome.__listeners.messages.length, 1);
    return new Promise((resolve) => {
      const keepAlive = chrome.__listeners.messages[0](message, sender, resolve);
      if (!keepAlive) resolve(undefined);
    });
  }

  return { calls, chrome, context, mediaQueue, sendMessage, storage };
}

function capturePayload(id = 'a') {
  return {
    url: `https://example.test/${id}`,
    title: `Capture ${id}`,
    text: `Visible body text for ${id} with enough content to capture.`
  };
}

test('service worker preserves queued captures while daemon is down and drains them after reload', async () => {
  const storage = { apiToken: 'token', daemonUrl: 'http://127.0.0.1:8765', policyMode: 'all' };
  let offline = true;
  let postCount = 0;
  const fetchImpl = async (url) => {
    if (url.endsWith('/capture')) {
      postCount += 1;
      if (offline) throw new Error('daemon-offline');
      return jsonResponse(201, { stored: true, document_id: 'doc-a', snapshot_id: 'snap-a', visit_id: 'visit-a', media_artifacts: [] });
    }
    throw new Error(`unexpected fetch ${url}`);
  };

  const first = createServiceWorkerHarness({ storage, fetchImpl });
  const failed = await first.sendMessage(
    { type: 'BMD_CAPTURE', payload: capturePayload('offline') },
    { tab: { id: 1, url: 'https://example.test/offline', active: true, incognito: false } }
  );

  assert.equal(failed.ok, true);
  assert.equal(failed.result.ok, false);
  assert.equal(failed.result.remaining, 1);
  assert.equal(storage.captureQueue.length, 1);
  assert.equal(storage.captureQueue[0].payload.url, 'https://example.test/offline');

  offline = false;
  const restarted = createServiceWorkerHarness({ storage, fetchImpl });
  const drained = await restarted.context.drainAllQueues();

  assert.equal(drained.captures.ok, true);
  assert.equal(drained.captures.remaining, 0);
  assert.equal(drained.captures.delivered[0].document_id, 'doc-a');
  assert.deepEqual(storage.captureQueue, []);
  assert.equal(postCount, 2);
});

test('service worker skips missing token and pause without mutating capture queue, then resumes', async () => {
  const storage = { daemonUrl: 'http://127.0.0.1:8765', policyMode: 'all', apiToken: '' };
  let postCount = 0;
  const fetchImpl = async (url) => {
    if (url.endsWith('/capture')) {
      postCount += 1;
      return jsonResponse(201, { stored: true, document_id: 'doc-resumed', snapshot_id: 'snap-resumed', visit_id: 'visit-resumed', media_artifacts: [] });
    }
    throw new Error(`unexpected fetch ${url}`);
  };
  const worker = createServiceWorkerHarness({ storage, fetchImpl });

  const missingToken = await worker.sendMessage({ type: 'BMD_CAPTURE', payload: capturePayload('missing-token') });
  assert.equal(missingToken.result.skipped, true);
  assert.equal(missingToken.result.reason, 'missing-token');
  assert.deepEqual(storage.captureQueue || [], []);

  await worker.chrome.storage.local.set({ apiToken: 'token', capturePaused: true });
  const paused = await worker.sendMessage({ type: 'BMD_CAPTURE', payload: capturePayload('paused') });
  assert.equal(paused.result.skipped, true);
  assert.equal(paused.result.reason, 'paused');
  assert.deepEqual(storage.captureQueue || [], []);

  await worker.chrome.storage.local.set({ capturePaused: false });
  const resumed = await worker.sendMessage({ type: 'BMD_CAPTURE', payload: capturePayload('resumed') });
  assert.equal(resumed.result.ok, true);
  assert.equal(resumed.result.remaining, 0);
  assert.deepEqual(storage.captureQueue, []);
  assert.equal(postCount, 1);
});

test('service worker injection respects stale token, pause, and strict URL controls', async () => {
  const storage = { apiToken: '', daemonUrl: 'http://127.0.0.1:8765', policyMode: 'strict' };
  const worker = createServiceWorkerHarness({ storage, fetchImpl: async () => jsonResponse(200, {}) });

  let result = await worker.context.maybeInjectCapture(7, 'https://example.test/ok');
  assert.equal(result.skipped, true);
  assert.equal(result.reason, 'missing-token');
  assert.deepEqual(worker.calls.scripts, []);

  await worker.chrome.storage.local.set({ apiToken: 'token' });
  result = await worker.context.maybeInjectCapture(7, 'https://bank.example.test/login');
  assert.equal(result.skipped, true);
  assert.equal(result.reason, 'blocked-url');
  assert.deepEqual(worker.calls.scripts, []);

  await worker.chrome.storage.local.set({ policyMode: 'all' });
  result = await worker.context.maybeInjectCapture(7, 'https://bank.example.test/login');
  assert.equal(result.ok, true);
  assert.equal(worker.calls.scripts.length, 1);
  result = await worker.context.maybeInjectCapture(7, 'https://bank.example.test/login');
  assert.equal(result.skipped, true);
  assert.equal(result.reason, 'already-injected');

  await worker.chrome.storage.local.set({ capturePaused: true });
  result = await worker.context.maybeInjectCapture(8, 'https://example.test/paused');
  assert.equal(result.skipped, true);
  assert.equal(result.reason, 'paused');
});

test('service worker media upload retries keep fetched blob until successful upload', async () => {
  const storage = { apiToken: 'token', daemonUrl: 'http://127.0.0.1:8765', policyMode: 'all' };
  let uploadAttempts = 0;
  const mediaQueue = new MemoryMediaQueueStore();
  await mediaQueue.putMediaTask({
    artifact_id: 'media-1',
    status: 'pending-upload',
    document_id: 'doc-1',
    snapshot_id: 'snap-1',
    visit_id: 'visit-1',
    page_url: 'https://example.test/page',
    source_url: 'https://example.test/image.png',
    media_type: 'image',
    mime_type: 'image/png'
  });
  await mediaQueue.putFetchedBlob('media-1', new Blob([new Uint8Array([1, 2, 3])], { type: 'image/png' }), { mime_type: 'image/png', byte_size: 3 });

  const fetchImpl = async (url) => {
    if (url.endsWith('/media-artifacts/media-1/blob')) {
      uploadAttempts += 1;
      if (uploadAttempts === 1) return jsonResponse(503, { error: 'temporary outage' });
      return jsonResponse(200, { stored: true, artifact_id: 'media-1', capture_status: 'stored' });
    }
    throw new Error(`unexpected fetch ${url}`);
  };
  const worker = createServiceWorkerHarness({ storage, fetchImpl, mediaQueue });

  const failedDrain = await worker.context.drainMediaQueue({ limit: 1 });
  assert.equal(failedDrain.ok, true);
  assert.equal(failedDrain.results[0].terminal, false);
  let task = (await mediaQueue.getDueMediaTasks(10, '2100-01-01T00:00:00.000Z'))[0];
  assert.equal(task.status, 'retrying');
  assert.equal(task.attempts, 1);
  assert.equal((await mediaQueue.getFetchedBlob('media-1')).metadata.byte_size, 3);

  await mediaQueue.markMediaTask('media-1', { status: 'retrying', next_attempt_at: '2000-01-01T00:00:00.000Z' });
  const successfulDrain = await worker.context.drainMediaQueue({ limit: 1 });

  assert.equal(successfulDrain.ok, true);
  assert.equal(successfulDrain.results[0].stored, true);
  assert.deepEqual(await mediaQueue.countMediaTasksByStatus(), {});
  assert.equal(await mediaQueue.getFetchedBlob('media-1'), null);
  assert.equal(uploadAttempts, 2);
});
