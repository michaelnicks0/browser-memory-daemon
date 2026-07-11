const test = require('node:test');
const assert = require('node:assert/strict');
const { MemoryOutboxStore } = require('../../src/outbox.js');
const { createCaptureBridge } = require('../../src/capture_bridge.js');
const { createTelemetry, sanitize, safeError } = require('../../src/telemetry.js');

function chromeStorage(initial = {}) {
  const storage = { ...initial };
  return {
    storage,
    chromeApi: {
      storage: {
        local: {
          async get(defaults) { return { ...(defaults || {}), ...storage }; },
          async set(values) { Object.assign(storage, values); },
          async remove(keys) { for (const key of Array.isArray(keys) ? keys : [keys]) delete storage[key]; }
        }
      }
    }
  };
}

function response(status, body = {}) {
  return { ok: status >= 200 && status < 300, status, async json() { return body; } };
}

function harness({ fetchImpl, config = {}, outbox = new MemoryOutboxStore(), mediaBridge = null } = {}) {
  const { chromeApi, storage } = chromeStorage();
  const telemetry = createTelemetry({ chromeApi, nowIso: () => '2030-01-01T00:00:00.000Z' });
  const media = mediaBridge || {
    queued: [],
    drains: 0,
    async queueMediaArtifacts(payload, result) { this.queued.push({ payload, result }); return { queued: 0 }; },
    scheduleMediaDrain() { this.drains += 1; }
  };
  let id = 0;
  const completeConfig = {
    daemonUrl: 'http://127.0.0.1:8765', apiToken: 'token', capturePaused: false,
    policyMode: 'all', captureQueue: [], visitEventQueue: [],
    captureOutboxMaxBytes: 1024 * 1024, lifecycleOutboxMaxBytes: 1024 * 1024,
    ...config
  };
  const bridge = createCaptureBridge({
    chromeApi,
    fetchImpl,
    getConfig: async () => ({ ...completeConfig, ...storage }),
    allowsIncognito: (mode) => mode === 'all',
    isTrackableUrl: (url) => !String(url).includes('blocked.test'),
    ensureCaptureIdentity(payload) {
      return { ...payload, observation_id: payload.observation_id || `obs-${++id}`, navigation_id: payload.navigation_id || `nav-${id}` };
    },
    randomId: (prefix) => `${prefix}-${++id}`,
    outboxApi: () => outbox,
    mediaQueueApi: () => ({ async getMediaQueueStats() { return { task_count: 0, blob_bytes: 0 }; } }),
    mediaBridge: media,
    telemetry,
    normalizeDaemonUrl: (value) => String(value).replace(/\/+$/, ''),
    authHeaders: (token) => ({ authorization: `Bearer ${token}`, 'content-type': 'application/json' }),
    nowIso: () => '2030-01-01T00:00:00.000Z',
    defaults: { captureOutboxMaxBytes: 1024 * 1024, lifecycleOutboxMaxBytes: 1024 * 1024 }
  });
  return { bridge, outbox, media, storage };
}

test('capture bridge retains a transactionally admitted capture during daemon outage and resumes once', async () => {
  let available = false;
  let capturePosts = 0;
  const { bridge, outbox, media } = harness({
    fetchImpl: async (url) => {
      assert.match(url, /\/capture$/);
      capturePosts += 1;
      return available ? response(200, { document_id: 'doc-1', snapshot_id: 'snap-1', media_artifacts: [] }) : response(503);
    }
  });

  const failed = await bridge.enqueueCapture({ url: 'https://page.test/', text: 'private evidence' });
  assert.equal(failed.ok, false);
  assert.equal((await outbox.getStats('capture')).count, 1);

  available = true;
  Array.from(outbox.items.values())[0].next_attempt_at = '2000-01-01T00:00:00.000Z';
  const recovered = await bridge.drainCaptureQueue();
  assert.equal(recovered.ok, true);
  assert.equal((await outbox.getStats('capture')).count, 0);
  assert.equal(capturePosts, 2);
  assert.equal(media.queued.length, 1);
});

test('capture bridge checkpoints daemon acceptance before media admission compensation', async () => {
  let posts = 0;
  let rejectMedia = true;
  const media = {
    scheduleMediaDrain() {},
    async queueMediaArtifacts() { if (rejectMedia) throw new Error('media quota https://private.test/item'); return { queued: 1 }; }
  };
  const { bridge, outbox, storage } = harness({
    mediaBridge: media,
    fetchImpl: async () => { posts += 1; return response(200, { document_id: 'doc-1', snapshot_id: 'snap-1', media_artifacts: [{ artifact_id: 'm1' }] }); }
  });

  const first = await bridge.enqueueCapture({ url: 'https://page.test/', media_artifacts: [{ src: 'https://cdn.test/a.png' }] });
  assert.equal(first.ok, false);
  assert.equal(posts, 1);
  assert.equal(Array.from(outbox.items.values())[0].capture_result.document_id, 'doc-1');
  assert.doesNotMatch(storage.lastCaptureOutboxError.error, /private\.test/);

  rejectMedia = false;
  Array.from(outbox.items.values())[0].next_attempt_at = '2000-01-01T00:00:00.000Z';
  const second = await bridge.drainCaptureQueue();
  assert.equal(second.ok, true);
  assert.equal(posts, 1);
});

test('capture bridge rejects blocked lifecycle events before outbox admission', async () => {
  const { bridge, outbox } = harness({ fetchImpl: async () => response(200, {}) });
  const result = await bridge.enqueueVisitEvent({ url: 'https://blocked.test/path' });
  assert.deepEqual(result, { skipped: true, reason: 'blocked-url' });
  assert.equal((await outbox.getStats('lifecycle')).count, 0);
});

test('telemetry recursively removes captured fields and redacts URLs from errors', () => {
  const cleaned = sanitize({
    payload: { text: 'secret' },
    page_url: 'https://private.test/path',
    pageUrl: 'https://private.test/camel',
    requestHeaders: { Cookie: 'secret' },
    counts: { pending: 2 },
    error: 'failed https://private.test/path'
  });
  assert.deepEqual(cleaned.counts, { pending: 2 });
  assert.equal('payload' in cleaned, false);
  assert.equal('page_url' in cleaned, false);
  assert.equal('pageUrl' in cleaned, false);
  assert.equal('requestHeaders' in cleaned, false);
  assert.equal(cleaned.error, 'failed [redacted-url]');
  assert.equal(safeError(new Error('fetch https://private.test/path failed')), 'fetch [redacted-url] failed');
});
