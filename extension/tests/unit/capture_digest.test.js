const test = require('node:test');
const assert = require('node:assert/strict');
const { webcrypto } = require('node:crypto');
const { stableJson, sha256Hex, captureDigest } = require('../../src/capture_digest.js');

test('portable SHA-256 fallback matches the standard vector', async () => {
  assert.equal(sha256Hex(new TextEncoder().encode('abc')), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  const payload = { url: 'http://insecure.example.test/', text: 'fallback digest payload' };
  assert.equal(await captureDigest(payload, null), await captureDigest(payload, webcrypto));
});

test('capture digest is deterministic across volatile capture time and object key order', async () => {
  const left = {
    url: 'https://example.test/article',
    title: 'Article',
    text: 'complete rendered text',
    captured_at: '2030-01-01T00:00:00Z',
    max_scroll_percent: 10,
    policy_mode: 'all',
    media_artifacts: [{ source_url: 'https://example.test/a.png', metadata: { z: 2, a: 1 } }]
  };
  const right = {
    ...left,
    captured_at: '2030-01-02T00:00:00Z',
    max_scroll_percent: 90,
    media_artifacts: [{ metadata: { a: 1, z: 2 }, source_url: 'https://example.test/a.png' }]
  };
  const leftDigest = await captureDigest(left, webcrypto);
  const rightDigest = await captureDigest(right, webcrypto);
  assert.match(leftDigest, /^sha256:[0-9a-f]{64}$/);
  assert.equal(leftDigest, rightDigest);
  assert.equal(stableJson({ z: 1, a: 2 }), '{"a":2,"z":1}');
});

test('capture digest detects middle-text and complete media-list changes missed by the legacy fingerprint', async () => {
  const common = {
    url: 'https://example.test/article',
    title: 'Article',
    policy_mode: 'all',
    text: `${'x'.repeat(300)}A${'y'.repeat(300)}`,
    media_artifacts: Array.from({ length: 21 }, (_, index) => ({ media_type: 'image', role: 'content', source_url: `https://example.test/${index}.png` }))
  };
  const middleChanged = { ...common, text: `${'x'.repeat(300)}B${'y'.repeat(300)}` };
  const lateMediaChanged = {
    ...common,
    media_artifacts: common.media_artifacts.map((item, index) => index === 20 ? { ...item, source_url: 'https://example.test/changed.png' } : item)
  };
  assert.notEqual(await captureDigest(common, webcrypto), await captureDigest(middleChanged, webcrypto));
  assert.notEqual(await captureDigest(common, webcrypto), await captureDigest(lateMediaChanged, webcrypto));
});
