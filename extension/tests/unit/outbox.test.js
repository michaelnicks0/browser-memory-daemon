const test = require('node:test');
const assert = require('node:assert/strict');

const { MemoryOutboxStore, serializedBytes } = require('../../src/outbox.js');

test('concurrent enqueue preserves existing captures and visibly rejects only new work at capacity', async () => {
  const outbox = new MemoryOutboxStore();
  const results = await Promise.all([
    outbox.enqueue('capture', { id: 'a' }, { maxItems: 2, queuedAt: '2030-01-01T00:00:00.000Z' }),
    outbox.enqueue('capture', { id: 'b' }, { maxItems: 2, queuedAt: '2030-01-01T00:00:01.000Z' }),
    outbox.enqueue('capture', { id: 'c' }, { maxItems: 2, queuedAt: '2030-01-01T00:00:02.000Z' })
  ]);

  assert.deepEqual(results.map((result) => result.accepted), [true, true, false]);
  assert.equal(results[2].reason, 'queue-full');
  assert.deepEqual((await outbox.list('capture')).map((item) => item.payload.id), ['a', 'b']);
  assert.equal((await outbox.getStats('capture')).count, 2);
});

test('claim, retry, due time, and acknowledgement are token-checked atomic transitions', async () => {
  const outbox = new MemoryOutboxStore();
  await outbox.enqueue('lifecycle', { event_id: 'event-1' }, { queuedAt: '2030-01-01T00:00:00.000Z' });

  const [claimed] = await outbox.claim('lifecycle', { claimToken: 'worker-a', now: '2030-01-01T00:01:00.000Z' });
  assert.equal(claimed.attempts, 1);
  assert.equal(await outbox.acknowledge(claimed.sequence_id, 'wrong-worker'), false);

  await outbox.retry(claimed.sequence_id, 'worker-a', {
    error: 'daemon-offline',
    nextAttemptAt: '2030-01-01T00:02:00.000Z'
  }, '2030-01-01T00:01:01.000Z');
  assert.deepEqual(await outbox.claim('lifecycle', { claimToken: 'worker-b', now: '2030-01-01T00:01:59.000Z' }), []);

  const [retried] = await outbox.claim('lifecycle', { claimToken: 'worker-b', now: '2030-01-01T00:02:00.000Z' });
  assert.equal(retried.sequence_id, claimed.sequence_id);
  assert.equal(retried.attempts, 2);
  assert.equal(await outbox.acknowledge(retried.sequence_id, 'worker-b'), true);
  const finalStats = await outbox.getStats('lifecycle');
  assert.equal(finalStats.count, 0);
  assert.ok(finalStats.last_success_at);
});

test('stale claims recover after service-worker suspension without becoming concurrently claimable', async () => {
  const outbox = new MemoryOutboxStore();
  await outbox.enqueue('capture', { observation_id: 'observation-1' }, { queuedAt: '2030-01-01T00:00:00.000Z' });
  const [claimed] = await outbox.claim('capture', {
    claimToken: 'suspended-worker',
    now: '2030-01-01T00:00:10.000Z',
    staleClaimMs: 60_000
  });

  assert.deepEqual(await outbox.claim('capture', {
    claimToken: 'early-worker',
    now: '2030-01-01T00:01:09.000Z',
    staleClaimMs: 60_000
  }), []);

  const [recovered] = await outbox.claim('capture', {
    claimToken: 'restarted-worker',
    now: '2030-01-01T00:01:10.000Z',
    staleClaimMs: 60_000
  });
  assert.equal(recovered.sequence_id, claimed.sequence_id);
  assert.equal(recovered.payload.observation_id, 'observation-1');
  assert.equal(recovered.attempts, 2);
});

test('legacy queue import is marked atomically and is idempotent before chrome storage cleanup', async () => {
  const outbox = new MemoryOutboxStore();
  const legacy = {
    captureQueue: [{ payload: { observation_id: 'legacy-capture' }, queued_at: '2030-01-01T00:00:00.000Z' }],
    visitEventQueue: [{ payload: { event_id: 'legacy-event' }, queued_at: '2030-01-01T00:00:01.000Z' }]
  };

  const first = await outbox.importLegacyQueues(legacy);
  const second = await outbox.importLegacyQueues(legacy);
  const rollbackCapture = { payload: { observation_id: 'rollback-capture' }, queued_at: '2030-01-01T00:00:02.000Z' };
  const third = await outbox.importLegacyQueues({ ...legacy, captureQueue: [...legacy.captureQueue, rollbackCapture] });

  assert.equal(first.state, 'imported');
  assert.equal(first.imported, 2);
  assert.equal(second.imported, 0);
  assert.equal(third.imported, 1);
  assert.equal((await outbox.list('capture')).length, 2);
  assert.equal((await outbox.list('lifecycle')).length, 1);
});

test('serialized byte accounting uses UTF-8 payload bytes and survives claim metadata changes', async () => {
  const outbox = new MemoryOutboxStore();
  const payload = { text: 'snowman ☃' };
  await outbox.enqueue('capture', payload);

  const before = await outbox.getStats('capture');
  assert.equal(before.serialized_bytes, serializedBytes(payload));
  const [claimed] = await outbox.claim('capture', { claimToken: 'worker' });
  assert.equal(claimed.serialized_bytes, before.serialized_bytes);
  assert.equal((await outbox.getStats('capture')).claimed, 1);
});

test('serialized byte quota rejects only the new row and reports required bytes', async () => {
  const outbox = new MemoryOutboxStore();
  const first = await outbox.enqueue('capture', { text: 'abc' }, { maxBytes: 100 });
  const second = await outbox.enqueue('capture', { text: 'x'.repeat(100) }, { maxBytes: 100 });

  assert.equal(first.accepted, true);
  assert.equal(second.accepted, false);
  assert.equal(second.reason, 'queue-bytes-full');
  assert.ok(second.required_bytes > 100);
  assert.equal((await outbox.list('capture')).length, 1);
});
