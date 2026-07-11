const test = require('node:test');
const assert = require('node:assert/strict');
const { MemoryMediaQueueStore } = require('../../src/media_queue.js');
const { createMediaBridge, mediaFetchSupported, inferMimeForTask } = require('../../src/media_bridge.js');

function response(status, body = {}, { headers = {}, arrayBuffer = new ArrayBuffer(0), blob = null } = {}) {
  const lowered = new Map(Object.entries(headers).map(([key, value]) => [key.toLowerCase(), String(value)]));
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => lowered.get(String(name).toLowerCase()) || '' },
    async json() { return body; },
    async arrayBuffer() { return arrayBuffer; },
    async blob() { return blob || new Blob([arrayBuffer], { type: lowered.get('content-type') || '' }); }
  };
}

function harness({ storage = {}, config = { daemonUrl: 'http://127.0.0.1:8765', apiToken: 'token', capturePaused: false }, fetchImpl, queue = new MemoryMediaQueueStore(), limits = {} } = {}) {
  const calls = [];
  const chromeApi = {
    storage: { local: { async set(values) { Object.assign(storage, values); } } },
    alarms: { create() {} }
  };
  const bridge = createMediaBridge({
    chromeApi,
    fetchImpl: async (url, init) => {
      calls.push({ url: String(url), init });
      if (!fetchImpl) throw new Error(`unexpected fetch ${url}`);
      return fetchImpl(String(url), init);
    },
    getConfig: async () => ({ ...config }),
    mediaQueueApi: () => queue,
    normalizeDaemonUrl: (value) => String(value).replace(/\/+$/, ''),
    authHeaders: (token) => ({ authorization: `Bearer ${token}`, 'content-type': 'application/json' }),
    nowIso: () => '2030-01-01T00:00:00.000Z',
    ...limits
  });
  return { bridge, queue, calls, storage };
}

test('media bridge maps capture artifacts into one atomic bounded task admission', async () => {
  const { bridge, queue } = harness({ limits: { maxQueueTasks: 1 } });
  const capture = { url: 'https://page.test/', visit_id: 'visit-1', media_artifacts: [{ src: 'https://cdn.test/a.png' }, { src: 'https://cdn.test/b.png' }] };
  const result = { document_id: 'doc-1', snapshot_id: 'snap-1', media_artifacts: [{ artifact_id: 'a' }, { artifact_id: 'b' }] };

  await assert.rejects(bridge.queueMediaArtifacts(capture, result), /media-task-quota/);
  assert.equal((await queue.getMediaQueueStats()).task_count, 0);
});

test('media bridge cleans terminal rows even while capture delivery is paused', async () => {
  const queue = new MemoryMediaQueueStore();
  await queue.putMediaTask({ artifact_id: 'expired', status: 'failed', updated_at: '2020-01-01T00:00:00.000Z' });
  const { bridge } = harness({ queue, config: { daemonUrl: 'http://127.0.0.1:8765', apiToken: 'token', capturePaused: true } });

  const result = await bridge.drainMediaQueue();
  assert.deepEqual(result, { skipped: true, reason: 'paused' });
  assert.equal((await queue.getMediaQueueStats()).task_count, 0);
});

test('media bridge keeps an admitted blob when upload fails so retry never refetches', async () => {
  const queue = new MemoryMediaQueueStore();
  await queue.putMediaTask({ artifact_id: 'media-1', source_url: 'https://cdn.test/media.png', document_id: 'doc-1', snapshot_id: 'snap-1' });
  let uploadAttempts = 0;
  const { bridge, calls } = harness({
    queue,
    fetchImpl: async (url) => {
      if (url === 'https://cdn.test/media.png') return response(200, {}, { headers: { 'content-type': 'image/png' }, arrayBuffer: new Uint8Array([1, 2, 3]).buffer });
      uploadAttempts += 1;
      return response(uploadAttempts === 1 ? 503 : 200, { stored: true });
    }
  });

  const first = await bridge.drainMediaQueue({ limit: 1 });
  assert.equal(first.results[0].terminal, false);
  assert.ok(await queue.getFetchedBlob('media-1'));
  await queue.markMediaTask('media-1', { status: 'retrying', next_attempt_at: '2000-01-01T00:00:00.000Z' });

  const second = await bridge.drainMediaQueue({ limit: 1 });
  assert.equal(second.results[0].stored, true);
  assert.equal(await queue.getFetchedBlob('media-1'), null);
  assert.equal(calls.filter((call) => call.url === 'https://cdn.test/media.png').length, 1);
});

test('media bridge URL and MIME helpers preserve credentialed-fetch boundaries', () => {
  assert.equal(mediaFetchSupported('https://cdn.test/video.mp4'), true);
  assert.equal(mediaFetchSupported('https://cdn.test/master.m3u8'), false);
  assert.equal(mediaFetchSupported('file:///tmp/not-allowed'), false);
  assert.equal(inferMimeForTask({ source_url: 'https://cdn.test/image.avif', media_type: 'image' }), 'image/avif');
});
