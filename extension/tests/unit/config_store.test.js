const test = require('node:test');
const assert = require('node:assert/strict');
const { DEFAULTS, CDP_RECORDER_DEFAULT_ON_MIGRATION_KEY, createConfigStore } = require('../../src/config_store.js');

function chromeStorage(initial = {}) {
  const state = { ...initial };
  const sets = [];
  return {
    state,
    sets,
    chromeApi: {
      storage: {
        local: {
          async get(defaults) { return { ...defaults, ...state }; },
          async set(values) { Object.assign(state, values); sets.push(values); }
        }
      }
    }
  };
}

test('config store applies the CDP default-on migration once and normalizes typed values', async () => {
  const storage = chromeStorage({ policyMode: 'STRICT', cdpRecorderEnabled: false });
  const store = createConfigStore({ chromeApi: storage.chromeApi, nowIso: () => '2030-01-01T00:00:00.000Z' });
  const first = await store.getConfig();
  assert.equal(first.policyMode, 'strict');
  assert.equal(first.cdpRecorderEnabled, true);
  assert.equal(storage.state[CDP_RECORDER_DEFAULT_ON_MIGRATION_KEY], '2030-01-01T00:00:00.000Z');
  assert.equal(storage.sets.length, 1);

  storage.state.cdpRecorderEnabled = false;
  const second = await store.getConfig();
  assert.equal(second.cdpRecorderEnabled, false);
  assert.equal(storage.sets.length, 1);
  assert.equal(store.allowsIncognito('all'), true);
  assert.equal(store.allowsIncognito('balanced'), false);
  assert.equal(DEFAULTS.captureOutboxMaxBytes, 32 * 1024 * 1024);
});

test('config store persists visit and CDP capture context maps independently', async () => {
  const storage = chromeStorage();
  const store = createConfigStore({ chromeApi: storage.chromeApi });
  await store.saveTabVisitState({ 7: { visitId: 'visit-7' } });
  await store.saveCdpCaptureContexts({ 7: { document_id: 'doc-7', snapshot_id: 'snap-7' } });
  assert.deepEqual(await store.getTabVisitState(), { 7: { visitId: 'visit-7' } });
  assert.deepEqual(await store.getCdpCaptureContexts(), { 7: { document_id: 'doc-7', snapshot_id: 'snap-7' } });
});
