(function () {
function stableHash(text) {
  let hash = 2166136261;
  for (const char of String(text || '')) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function stableVisitEventId(state, eventType, segmentStartedAt) {
  return `vevt_${stableHash([state.visitId, eventType, segmentStartedAt, state.url].join('|'))}`;
}

function secondsBetween(startIso, endIso) {
  const start = Date.parse(startIso || '');
  const end = Date.parse(endIso || '');
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return 0;
  return Math.max(0, Math.round((end - start) / 1000));
}

function sanitizedScrollPercent(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(100, Math.round(parsed)));
}

function createVisitTracker({ configStore, getConfig, isTrackableUrl, enqueueVisitEvent, ensureCaptureIdentity, randomId, nowIso = () => new Date().toISOString() } = {}) {
  if (!configStore || typeof getConfig !== 'function' || typeof enqueueVisitEvent !== 'function') throw new Error('visit tracker dependencies unavailable');

  async function emitVisitEventForState(state, eventType, endedAt = nowIso()) {
    const config = await getConfig();
    if (!state || !state.url || !state.visitId || !isTrackableUrl(state.url, config.policyMode)) return { skipped: true, reason: 'missing-state' };
    const segmentStartedAt = state.activeStartedAt || state.visitStartedAt || endedAt;
    return enqueueVisitEvent({
      event_id: stableVisitEventId(state, eventType, segmentStartedAt),
      visit_id: state.visitId,
      url: state.url,
      event_type: eventType,
      event_started_at: segmentStartedAt,
      event_ended_at: endedAt,
      active_seconds: state.activeStartedAt ? secondsBetween(state.activeStartedAt, endedAt) : 0,
      max_scroll_percent: sanitizedScrollPercent(state.maxScrollPercent),
      metadata: { tab_id: state.tabId }
    });
  }

  async function finishActiveSegmentsExcept(activeTabId, eventType = 'tab-deactivated') {
    const states = await configStore.getTabVisitState();
    const endedAt = nowIso();
    const deliveries = [];
    for (const [key, state] of Object.entries(states)) {
      if (String(activeTabId) === key || !state || !state.activeStartedAt) continue;
      deliveries.push(emitVisitEventForState({ ...state }, eventType, endedAt));
      state.activeStartedAt = null;
      states[key] = state;
    }
    await configStore.saveTabVisitState(states);
    return Promise.allSettled(deliveries);
  }

  async function finishTabVisit(tabId, eventType = 'tab-deactivated', { remove = false } = {}) {
    const key = String(tabId);
    const states = await configStore.getTabVisitState();
    const state = states[key];
    if (!state) return { skipped: true, reason: 'missing-state' };
    const result = await emitVisitEventForState(state, eventType, nowIso());
    if (remove) delete states[key];
    else {
      state.activeStartedAt = null;
      states[key] = state;
    }
    await configStore.saveTabVisitState(states);
    return result;
  }

  async function ensureVisitState(tabId, url) {
    const config = await getConfig();
    if (config.capturePaused || !config.apiToken || !isTrackableUrl(url, config.policyMode)) return null;
    const key = String(tabId);
    let states = await configStore.getTabVisitState();
    let state = states[key];
    if (state && state.url !== url) {
      await finishTabVisit(tabId, 'navigation-away', { remove: true });
      states = await configStore.getTabVisitState();
      state = null;
    }
    if (!state) {
      state = {
        tabId,
        url,
        visitId: randomId('visit'),
        navigationId: randomId('navigation'),
        visitStartedAt: nowIso(),
        activeStartedAt: null,
        maxScrollPercent: 0
      };
    } else if (!state.navigationId) state.navigationId = randomId('navigation');
    states[key] = state;
    await configStore.saveTabVisitState(states);
    return state;
  }

  async function markTabActive(tabId, url) {
    await finishActiveSegmentsExcept(tabId, 'tab-deactivated');
    const state = await ensureVisitState(tabId, url);
    if (!state) return { skipped: true, reason: 'untrackable-tab' };
    if (!state.activeStartedAt) state.activeStartedAt = nowIso();
    const states = await configStore.getTabVisitState();
    states[String(tabId)] = state;
    await configStore.saveTabVisitState(states);
    return { ok: true, visit_id: state.visitId };
  }

  async function updateStateFromPayload(tabId, payload) {
    const state = await ensureVisitState(tabId, payload.url);
    if (!state) return null;
    state.maxScrollPercent = Math.max(sanitizedScrollPercent(state.maxScrollPercent), sanitizedScrollPercent(payload.max_scroll_percent));
    const states = await configStore.getTabVisitState();
    states[String(tabId)] = state;
    await configStore.saveTabVisitState(states);
    return state;
  }

  async function decorateCapturePayload(payload, sender) {
    const config = await getConfig();
    const tab = sender?.tab || null;
    const decorated = { ...payload, is_incognito: Boolean(tab?.incognito), policy_mode: configStore.normalizePolicyMode(config.policyMode) };
    if (!tab || typeof tab.id !== 'number' || !decorated.url || !isTrackableUrl(decorated.url, config.policyMode)) return ensureCaptureIdentity(decorated);
    const state = await updateStateFromPayload(tab.id, decorated);
    if (!state) return ensureCaptureIdentity(decorated);
    if (tab.active && !state.activeStartedAt) {
      state.activeStartedAt = state.visitStartedAt || nowIso();
      const states = await configStore.getTabVisitState();
      states[String(tab.id)] = state;
      await configStore.saveTabVisitState(states);
    }
    decorated.visit_id = state.visitId;
    decorated.navigation_id = state.navigationId;
    decorated.visit_started_at = state.visitStartedAt;
    return ensureCaptureIdentity(decorated);
  }

  return { emitVisitEventForState, finishActiveSegmentsExcept, finishTabVisit, ensureVisitState, markTabActive, updateStateFromPayload, decorateCapturePayload };
}

const api = { stableHash, stableVisitEventId, secondsBetween, sanitizedScrollPercent, createVisitTracker };
globalThis.BrowserMemoryVisitTracker = api;
if (typeof module !== 'undefined') module.exports = api;
})();
