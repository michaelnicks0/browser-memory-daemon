const test = require('node:test');
const assert = require('node:assert/strict');
const { MemoryQueue } = require('../../src/queue.js');

test('queue preserves FIFO order', () => {
  const queue = new MemoryQueue();
  assert.equal(queue.enqueue({ id: 1 }), 1);
  assert.equal(queue.enqueue({ id: 2 }), 2);
  assert.equal(queue.peek().id, 1);
  assert.equal(queue.shift().id, 1);
  assert.equal(queue.shift().id, 2);
  assert.equal(queue.shift(), null);
});
