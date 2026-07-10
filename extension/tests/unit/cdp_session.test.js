const test = require('node:test');
const assert = require('node:assert/strict');
const { createCdpSession, createCdpRecorderController } = require('../../src/cdp_session.js');

function configStore(initial = {}) {
  let contexts = { ...initial };
  return {
    async getCdpCaptureContexts() { return { ...contexts }; },
    async saveCdpCaptureContexts(value) { contexts = { ...value }; },
    snapshot() { return contexts; }
  };
}

function chromeDebugger({ attachError = '', targets = [] } = {}) {
  const runtime = { lastError: null };
  return {
    runtime,
    debugger: {
      attach(_target, _version, callback) {
        runtime.lastError = attachError ? { message: attachError } : null;
        callback();
        runtime.lastError = null;
      },
      detach(_target, callback) { callback(); },
      sendCommand(_target, _method, _params, callback) { callback({}); },
      getTargets(callback) { callback(targets); }
    }
  };
}

test('CDP session restores capture provenance and clears it on tab URL reuse', async () => {
  const store = configStore({ 7: { document_id: 'doc-7', snapshot_id: 'snap-7', page_url: 'https://x.com/a' } });
  const session = createCdpSession({ chromeApi: chromeDebugger(), configStore: store, nowIso: () => '2030-01-01T00:00:00.000Z' });
  assert.equal((await session.getCaptureContext(7)).document_id, 'doc-7');
  assert.equal(await session.clearCaptureContextIfUrlChanged(7, 'https://x.com/a'), false);
  assert.equal(await session.clearCaptureContextIfUrlChanged(7, 'https://x.com/b'), true);
  assert.equal(await session.getCaptureContext(7), null);
  assert.deepEqual(store.snapshot(), {});

  await session.rememberCaptureContext(7, { document_id: 'doc-new', snapshot_id: 'snap-new', page_url: 'https://x.com/b' });
  assert.equal(store.snapshot()['7'].persisted_at, '2030-01-01T00:00:00.000Z');
});

test('CDP session reconstructs an attachment already owned by the extension after worker restart', async () => {
  const session = createCdpSession({
    chromeApi: chromeDebugger({ attachError: 'Another debugger is already attached', targets: [{ tabId: 9, attached: true }] }),
    configStore: configStore()
  });
  assert.deepEqual(await session.attachOrRecover(9), { attached: true, recovered: true });
});

test('CDP session does not hide an attach failure without matching attached target evidence', async () => {
  const session = createCdpSession({ chromeApi: chromeDebugger({ attachError: 'attach denied', targets: [] }), configStore: configStore() });
  await assert.rejects(() => session.attachOrRecover(11), /attach denied/);
});

test('CDP capture-context writes serialize so tab close cannot be overwritten by a slower capture write', async () => {
  let stored = {};
  let writes = 0;
  const store = {
    async getCdpCaptureContexts() { return {}; },
    async saveCdpCaptureContexts(value) {
      writes += 1;
      if (writes === 1) await new Promise((resolve) => setTimeout(resolve, 20));
      stored = structuredClone(value);
    }
  };
  const session = createCdpSession({ chromeApi: chromeDebugger(), configStore: store });
  const remember = session.rememberCaptureContext(7, { document_id: 'doc-7', snapshot_id: 'snap-7', page_url: 'https://x.com/a' });
  const clear = session.clearCaptureContext(7);
  await Promise.all([remember, clear]);
  assert.deepEqual(stored, {});
  assert.equal(await session.getCaptureContext(7), null);
});

test('CDP recorder controller owns response correlation and media-body delivery outside the service worker', async () => {
  const state = { commands: [], cleared: [], detached: [] };
  const session = {
    recorderByTab: new Map(),
    captureContextByTab: new Map(),
    async ready() {},
    async clearCaptureContextIfUrlChanged(tabId, url) { state.cleared.push([tabId, url]); },
    async attachOrRecover() { return { attached: true, recovered: true }; },
    async command(tabId, method) {
      state.commands.push([tabId, method]);
      return method === 'Network.getResponseBody' ? { base64Encoded: false, body: 'video-bytes' } : {};
    },
    async getCaptureContext() { return { document_id: 'doc-1', snapshot_id: 'snap-1', visit_id: 'visit-1', page_url: 'https://x.com/post' }; },
    async clearCaptureContext(tabId) { state.cleared.push([tabId, null]); },
    async detach(tabId) { state.detached.push(tabId); }
  };
  const recorderApi = {
    DEFAULT_CDP_RECORDER_DOMAINS: ['x.com'],
    DEFAULT_CDP_MEDIA_HOSTS: ['video.twimg.com'],
    normalizeDomains(value, fallback) { return value || fallback; },
    shouldRecordTabUrl() { return true; },
    cdpMediaCandidate() { return { source_url: 'https://video.twimg.com/segment.mp4', mime_type: 'video/mp4', role: 'cdp-segment', is_manifest: false }; },
    cdpMediaArtifactPayload(context, candidate, extra = {}) { return { ...context, ...candidate, ...extra }; },
    approxBase64Bytes(value) { return String(value).length; },
    cdpBodyToBlob(body, mime) { return new Blob([body.body], { type: mime }); }
  };
  const uploads = [];
  const mediaBridge = {
    async postMediaArtifact() { return { artifact_id: 'artifact-1' }; },
    async putMediaArtifactBlob(task, blob) { uploads.push({ task, blob }); return { stored: true }; },
    async fetchPendingMediaArtifacts() { return {}; }
  };
  const telemetry = { async record() {}, async recordError() {}, safeError: (error) => String(error.message || error) };
  const controller = createCdpRecorderController({
    chromeApi: { debugger: { attach() {} } }, session, recorderApi, mediaBridge, telemetry,
    getConfig: async () => ({ apiToken: 'token', capturePaused: false, cdpRecorderEnabled: true })
  });

  assert.deepEqual(await controller.ensureRecorder(4, 'https://x.com/post'), { ok: true, attached: true, recovered: true });
  controller.handleEvent({ tabId: 4 }, 'Network.responseReceived', { requestId: 'request-1', response: {}, type: 'Media' });
  controller.handleEvent({ tabId: 4 }, 'Network.loadingFinished', { requestId: 'request-1', encodedDataLength: 11 });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(uploads.length, 1);
  assert.equal(uploads[0].task.document_id, 'doc-1');
  assert.deepEqual(state.commands.map((item) => item[1]), ['Network.enable', 'Network.getResponseBody']);
  controller.removeTab(4);
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(state.detached, [4]);
});
