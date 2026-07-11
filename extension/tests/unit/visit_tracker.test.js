const test = require('node:test');
const assert = require('node:assert/strict');
const { stableVisitEventId, secondsBetween, sanitizedScrollPercent, createVisitTracker } = require('../../src/visit_tracker.js');

function stateStore(initial = {}) {
  let states = { ...initial };
  return {
    normalizePolicyMode(value) { return String(value || 'all').toLowerCase(); },
    async getTabVisitState() { return structuredClone(states); },
    async saveTabVisitState(value) { states = structuredClone(value); },
    snapshot() { return structuredClone(states); }
  };
}

test('visit identity helpers are deterministic and bound interval values', () => {
  const state = { visitId: 'visit-1', url: 'https://example.test', activeStartedAt: '2030-01-01T00:00:00.000Z' };
  assert.equal(stableVisitEventId(state, 'tab-closed', state.activeStartedAt), stableVisitEventId(state, 'tab-closed', state.activeStartedAt));
  assert.equal(secondsBetween('2030-01-01T00:00:00.000Z', '2030-01-01T00:00:05.400Z'), 5);
  assert.equal(secondsBetween('bad', '2030-01-01T00:00:05.000Z'), 0);
  assert.equal(sanitizedScrollPercent(120), 100);
  assert.equal(sanitizedScrollPercent(-1), 0);
});

test('visit tracker preserves navigation identity for repeated captures and closes prior URL state', async () => {
  const configStore = stateStore();
  const events = [];
  let id = 0;
  const tracker = createVisitTracker({
    configStore,
    getConfig: async () => ({ apiToken: 'token', capturePaused: false, policyMode: 'all' }),
    isTrackableUrl: () => true,
    enqueueVisitEvent: async (payload) => { events.push(payload); return { ok: true }; },
    ensureCaptureIdentity(payload) { return { ...payload, observation_id: payload.observation_id || `observation-${++id}` }; },
    randomId(prefix) { return `${prefix}-${++id}`; },
    nowIso: () => '2030-01-01T00:00:00.000Z'
  });

  const sender = { tab: { id: 7, active: true, incognito: false } };
  const first = await tracker.decorateCapturePayload({ url: 'https://example.test/a', max_scroll_percent: 20 }, sender);
  const second = await tracker.decorateCapturePayload({ url: 'https://example.test/a', max_scroll_percent: 60 }, sender);
  assert.equal(second.navigation_id, first.navigation_id);
  assert.equal(second.visit_id, first.visit_id);
  assert.notEqual(second.observation_id, first.observation_id);
  assert.equal(configStore.snapshot()['7'].maxScrollPercent, 60);

  const third = await tracker.decorateCapturePayload({ url: 'https://example.test/b' }, sender);
  assert.notEqual(third.navigation_id, first.navigation_id);
  assert.notEqual(third.visit_id, first.visit_id);
  assert.equal(events.length, 1);
  assert.equal(events[0].event_type, 'navigation-away');
  assert.equal(events[0].url, 'https://example.test/a');
});
