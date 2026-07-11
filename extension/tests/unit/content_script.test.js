const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const { TextEncoder } = require('node:util');

const DIGEST_SOURCE = fs.readFileSync(path.join(__dirname, '../../src/capture_digest.js'), 'utf8');
const CONTENT_SOURCE = fs.readFileSync(path.join(__dirname, '../../src/content_script.js'), 'utf8');

async function waitFor(predicate, timeoutMs = 2000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 1));
  }
  throw new Error('timed out waiting for content-script transition');
}

test('content capture retries the same full digest until admission succeeds and then suppresses duplicates', async () => {
  const sent = [];
  const responses = [{ ok: false, error: 'queue-unavailable' }, { ok: true, result: {} }];
  const element = { scrollTop: 0, scrollHeight: 100, clientHeight: 100 };
  const context = {
    crypto: webcrypto,
    TextEncoder,
    document: { documentElement: element, body: element },
    history: { pushState() {}, replaceState() {} },
    innerHeight: 100,
    scrollY: 0,
    addEventListener() {},
    setTimeout() {},
    fetch: async () => { throw new Error('unexpected fetch'); },
    extractPageFromDocument() {
      return {
        url: 'https://example.test/article',
        title: 'Article',
        text: `${'a'.repeat(300)}complete middle${'z'.repeat(300)}`,
        captured_at: new Date().toISOString(),
        extraction_method: 'dom-all-rendered-text-v2',
        policy_mode: 'all',
        media_artifacts: []
      };
    },
    normalizeBrowserMemoryPolicyMode(value) { return value || 'all'; },
    chrome: {
      storage: { local: { async get(defaults) { return defaults; } } },
      runtime: {
        lastError: null,
        sendMessage(message, callback) {
          sent.push(message);
          callback(responses.shift() || { ok: true, result: {} });
        }
      }
    }
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(DIGEST_SOURCE, context, { filename: 'capture_digest.js' });
  vm.runInContext(CONTENT_SOURCE, context, { filename: 'content_script.js' });

  context.__BMD_CAPTURE_NOW('retry-one');
  await waitFor(() => sent.length === 1 && context.__BMD_CAPTURE_IN_PROGRESS === false);
  assert.equal(sent.length, 1);
  assert.match(sent[0].payload.capture_digest, /^sha256:[0-9a-f]{64}$/);
  assert.equal(context.__BMD_LAST_CAPTURE_KEY, '');

  context.__BMD_CAPTURE_NOW('retry-two');
  await waitFor(() => sent.length === 2 && context.__BMD_CAPTURE_IN_PROGRESS === false);
  assert.equal(sent.length, 2);
  assert.equal(sent[1].payload.capture_digest, sent[0].payload.capture_digest);
  assert.equal(context.__BMD_LAST_CAPTURE_KEY, sent[0].payload.capture_digest);

  context.__BMD_CAPTURE_NOW('duplicate');
  await waitFor(() => context.__BMD_LAST_CAPTURE_STATUS.reason === 'duplicate-payload');
  assert.equal(sent.length, 2);
  assert.equal(context.__BMD_LAST_CAPTURE_STATUS.reason, 'duplicate-payload');
});
