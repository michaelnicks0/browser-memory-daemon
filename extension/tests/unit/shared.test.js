const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeDaemonUrl, authHeaders } = require('../../src/shared.js');

test('daemon URL normalization strips trailing slashes', () => {
  assert.equal(normalizeDaemonUrl('http://127.0.0.1:8765///'), 'http://127.0.0.1:8765');
  assert.equal(normalizeDaemonUrl(''), 'http://127.0.0.1:8765');
});

test('auth headers include bearer token', () => {
  assert.equal(authHeaders('abc').authorization, 'Bearer abc');
});
