const test = require('node:test');
const assert = require('node:assert/strict');
const { MemoryMediaQueueStore, normalizeTask } = require('../../src/media_queue.js');

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
  await queue.putFetchedBlob('m1', new Uint8Array([1, 2, 3]).buffer, { mime_type: 'image/png' });
  await queue.markMediaTask('m1', { status: 'pending-upload' });
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
