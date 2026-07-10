const test = require('node:test');
const assert = require('node:assert/strict');
const { CONTENT_SCRIPT_FILES, createInjectionController } = require('../../src/injection.js');

function chromeMock({ tabs = [] } = {}) {
  const scripts = [];
  const activeMarks = [];
  const storage = {};
  const chromeApi = {
    runtime: { lastError: null },
    storage: { local: { async set(value) { Object.assign(storage, value); } } },
    scripting: { async executeScript(spec) { scripts.push(spec); } },
    tabs: { query(_query, callback) { callback(tabs); } }
  };
  return { chromeApi, scripts, activeMarks, storage };
}

test('injection controller re-injects the complete ordered script set instead of trusting worker memory', async () => {
  const mock = chromeMock();
  let cdpEnsures = 0;
  const controller = createInjectionController({
    chromeApi: mock.chromeApi,
    getConfig: async () => ({ apiToken: 'token', capturePaused: false, policyMode: 'all' }),
    isTrackableUrl: () => true,
    ensureCdpRecorder: async () => { cdpEnsures += 1; }
  });
  assert.deepEqual(await controller.maybeInjectCapture(7, 'https://example.test/a'), { ok: true });
  assert.deepEqual(await controller.maybeInjectCapture(7, 'https://example.test/a'), { ok: true });
  assert.equal(cdpEnsures, 2);
  assert.deepEqual(mock.scripts.map((item) => item.files), [Array.from(CONTENT_SCRIPT_FILES), Array.from(CONTENT_SCRIPT_FILES)]);
});

test('injection controller preserves pause, token, and policy gates', async () => {
  const mock = chromeMock();
  let config = { apiToken: '', capturePaused: false, policyMode: 'all' };
  const controller = createInjectionController({
    chromeApi: mock.chromeApi,
    getConfig: async () => config,
    isTrackableUrl: (_url, policyMode) => policyMode === 'all'
  });
  assert.equal((await controller.maybeInjectCapture(1, 'https://example.test')).reason, 'missing-token');
  config = { apiToken: 'token', capturePaused: true, policyMode: 'all' };
  assert.equal((await controller.maybeInjectCapture(1, 'https://example.test')).reason, 'paused');
  config = { apiToken: 'token', capturePaused: false, policyMode: 'strict' };
  assert.equal((await controller.maybeInjectCapture(1, 'https://example.test')).reason, 'blocked-url');
  assert.equal(mock.scripts.length, 0);
});

test('startup reconstruction revisits every active tab', async () => {
  const mock = chromeMock({ tabs: [{ id: 3, url: 'https://example.test/a' }, { id: 4, url: 'https://example.test/b' }, { id: 5 }] });
  const marked = [];
  const controller = createInjectionController({
    chromeApi: mock.chromeApi,
    getConfig: async () => ({ apiToken: 'token', capturePaused: false, policyMode: 'all' }),
    isTrackableUrl: () => true,
    markTabActive(tabId, url) { marked.push([tabId, url]); }
  });
  controller.bootstrapActiveTabs();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(marked, [[3, 'https://example.test/a'], [4, 'https://example.test/b']]);
  assert.deepEqual(mock.scripts.map((item) => item.target.tabId), [3, 4]);

  controller.bootstrapActiveTabs({ markActive: false });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(marked, [[3, 'https://example.test/a'], [4, 'https://example.test/b']]);
  assert.deepEqual(mock.scripts.map((item) => item.target.tabId), [3, 4, 3, 4]);
});
