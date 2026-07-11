const test = require('node:test');
const assert = require('node:assert/strict');
const { MemoryMediaQueueStore, mediaTaskIsDue, normalizeTask } = require('../../src/media_queue.js');

test('media task normalization and due ordering', async () => {
  const queue = new MemoryMediaQueueStore();
  await queue.putMediaTask({ artifact_id: 'b', source_url: 'https://example.test/b.png', priority: 80 });
  await queue.putMediaTask({ artifact_id: 'a', source_url: 'https://example.test/a.png', priority: 10 });
  const due = await queue.getDueMediaTasks(10, '2030-01-01T00:00:00.000Z');
  assert.deepEqual(due.map((task) => task.artifact_id), ['b', 'a']);
  assert.equal(due[0].status, 'pending-fetch');
});

test('media queue retains fetched blob until task delete', async () => {
  const queue = new MemoryMediaQueueStore();
  await queue.putMediaTask({ artifact_id: 'm1', source_url: 'https://example.test/m1.png' });
  const admitted = await queue.putFetchedBlob('m1', new Uint8Array([1, 2, 3]).buffer, { mime_type: 'image/png' });
  assert.equal(admitted.accepted, true);
  assert.equal((await queue.getFetchedBlob('m1')).metadata.mime_type, 'image/png');
  assert.deepEqual(await queue.countMediaTasksByStatus(), { 'pending-upload': 1 });
  await queue.deleteMediaTask('m1');
  assert.equal(await queue.getFetchedBlob('m1'), null);
  assert.deepEqual(await queue.countMediaTasksByStatus(), {});
});

test('future retry is not due until next_attempt_at', async () => {
  const queue = new MemoryMediaQueueStore();
  await queue.putMediaTask({ artifact_id: 'retry', status: 'retrying', next_attempt_at: '2030-01-01T00:00:00.000Z' });
  assert.equal((await queue.getDueMediaTasks(10, '2029-01-01T00:00:00.000Z')).length, 0);
  assert.equal((await queue.getDueMediaTasks(10, '2030-01-01T00:00:00.000Z')).length, 1);
});

test('stale fetching and uploading tasks become due after processing window', async () => {
  const queue = new MemoryMediaQueueStore();
  await queue.putMediaTask({ artifact_id: 'fresh', status: 'fetching', updated_at: '2030-01-01T00:00:00.000Z' });
  await queue.putMediaTask({ artifact_id: 'stale', status: 'uploading', updated_at: '2029-12-31T23:55:00.000Z' });
  const due = await queue.getDueMediaTasks(10, '2030-01-01T00:00:30.000Z');
  assert.deepEqual(due.map((task) => task.artifact_id), ['stale']);
});

test('normalizeTask requires stable artifact id for queue callers', () => {
  const task = normalizeTask({ artifact_id: 'abc', source_url: 'data:image/png;base64,AA==' });
  assert.equal(task.artifact_id, 'abc');
  assert.equal(task.max_attempts, 5);
});

test('media task due-state classifier rejects terminal and malformed processing states', () => {
  const now = '2030-01-01T00:10:00.000Z';
  for (const status of ['succeeded', 'failed', 'skipped', 'expired', 'purged']) {
    assert.equal(mediaTaskIsDue({ status, updated_at: '2029-01-01T00:00:00.000Z' }, now), false);
  }
  assert.equal(mediaTaskIsDue({ status: 'fetching', updated_at: 'not-a-date' }, now), false);
  assert.equal(mediaTaskIsDue({ status: 'pending-fetch', next_attempt_at: null }, now), true);
});

test('media task batch admission is atomic and preserves existing work at count quota', async () => {
  const queue = new MemoryMediaQueueStore();
  await queue.putMediaTask({ artifact_id: 'existing' });
  const rejected = await queue.putMediaTasks([{ artifact_id: 'new-a' }, { artifact_id: 'new-b' }], { maxItems: 2 });
  assert.equal(rejected.accepted, false);
  assert.equal(rejected.reason, 'media-task-quota');
  assert.equal((await queue.getMediaQueueStats()).task_count, 1);

  const results = await Promise.all([
    queue.putMediaTasks([{ artifact_id: 'new-a' }], { maxItems: 2 }),
    queue.putMediaTasks([{ artifact_id: 'new-b' }], { maxItems: 2 })
  ]);
  assert.deepEqual(results.map((result) => result.accepted).sort(), [false, true]);
  assert.equal((await queue.getMediaQueueStats()).task_count, 2);
});

test('media blob admission atomically applies replacement-aware byte quota and task transition', async () => {
  const queue = new MemoryMediaQueueStore();
  await queue.putMediaTasks([{ artifact_id: 'a' }, { artifact_id: 'b' }]);
  const first = await queue.putFetchedBlob('a', new Uint8Array(3).buffer, {}, { maxTotalBytes: 4, maxBlobBytes: 4 });
  assert.equal(first.accepted, true);
  assert.equal(first.task.status, 'pending-upload');

  const rejected = await queue.putFetchedBlob('b', new Uint8Array(3).buffer, {}, { maxTotalBytes: 4, maxBlobBytes: 4 });
  assert.equal(rejected.accepted, false);
  assert.equal(rejected.reason, 'media-blob-total-quota');
  assert.equal((await queue.getMediaQueueStats()).blob_bytes, 3);
  assert.equal((await queue.getDueMediaTasks()).find((task) => task.artifact_id === 'b').status, 'pending-fetch');

  const replacement = await queue.putFetchedBlob('a', new Uint8Array(4).buffer, {}, { maxTotalBytes: 4, maxBlobBytes: 4 });
  assert.equal(replacement.accepted, true);
  assert.equal((await queue.getMediaQueueStats()).blob_bytes, 4);
});

test('terminal media quarantine cleanup retains fresh rows and atomically removes expired task and blob', async () => {
  const queue = new MemoryMediaQueueStore();
  await queue.putMediaTasks([{ artifact_id: 'old' }, { artifact_id: 'fresh' }]);
  await queue.putFetchedBlob('old', new Uint8Array(2).buffer);
  await queue.putFetchedBlob('fresh', new Uint8Array(3).buffer);
  await queue.markMediaTask('old', { status: 'failed' }, '2030-01-01T00:00:00.000Z');
  await queue.markMediaTask('fresh', { status: 'failed' }, '2030-01-02T00:00:00.000Z');

  const cleaned = await queue.cleanupTerminalMediaTasks({ now: '2030-01-02T12:00:00.000Z', ttlMs: 24 * 60 * 60 * 1000 });
  assert.deepEqual(cleaned.deleted, ['old']);
  assert.equal(await queue.getFetchedBlob('old'), null);
  assert.notEqual(await queue.getFetchedBlob('fresh'), null);
  assert.deepEqual(await queue.countMediaTasksByStatus(), { failed: 1 });
});
