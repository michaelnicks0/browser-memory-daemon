const test = require('node:test');
const assert = require('node:assert/strict');
const { createCdpSession } = require('../../src/cdp_session.js');

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
