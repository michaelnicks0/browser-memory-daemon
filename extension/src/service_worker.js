try { importScripts('shared.js', 'extractor.js'); } catch (_) {}

const DEFAULTS = {
  daemonUrl: 'http://127.0.0.1:8765',
  apiToken: '',
  capturePaused: false,
  policyMode: 'all',
  captureQueue: [],
  visitEventQueue: [],
  tabVisitState: {}
};

const MAX_CAPTURE_QUEUE = 100;
const MAX_VISIT_EVENT_QUEUE = 200;
const MAX_MEDIA_ARTIFACTS_PER_CAPTURE = 50;
const MAX_MEDIA_ARTIFACT_BYTES = 25_000_000;

function nowIso() {
  return new Date().toISOString();
}

function randomId(prefix = 'id') {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
    return `${prefix}_${globalThis.crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

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

function normalizePolicyMode(policyMode) {
  if (globalThis.normalizeBrowserMemoryPolicyMode) return globalThis.normalizeBrowserMemoryPolicyMode(policyMode);
  const mode = String(policyMode || 'all').toLowerCase();
  return ['all', 'recall', 'balanced', 'strict'].includes(mode) ? mode : 'all';
}

function allowsIncognito(policyMode) {
  return normalizePolicyMode(policyMode) === 'all';
}

function isTrackableUrl(url, policyMode = 'all') {
  if (!url) return false;
  if (normalizePolicyMode(policyMode) === 'all') return true;
  return !(globalThis.shouldBlockBrowserMemoryUrl && globalThis.shouldBlockBrowserMemoryUrl(url, { policyMode }));
}

async function getConfig() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...stored, policyMode: normalizePolicyMode(stored.policyMode || DEFAULTS.policyMode) };
}

async function saveQueue(queue) {
  await chrome.storage.local.set({ captureQueue: queue.slice(0, MAX_CAPTURE_QUEUE) });
}

async function saveVisitEventQueue(queue) {
  await chrome.storage.local.set({ visitEventQueue: queue.slice(0, MAX_VISIT_EVENT_QUEUE) });
}

async function getTabVisitState() {
  const stored = await chrome.storage.local.get({ tabVisitState: {} });
  return stored.tabVisitState && typeof stored.tabVisitState === 'object' ? stored.tabVisitState : {};
}

async function saveTabVisitState(state) {
  await chrome.storage.local.set({ tabVisitState: state });
}

async function postOne(payload, config) {
  const base = normalizeDaemonUrl(config.daemonUrl);
  const response = await fetch(`${base}/capture`, {
    method: 'POST',
    headers: authHeaders(config.apiToken),
    body: JSON.stringify(payload),
    targetAddressSpace: 'loopback'
  });
  if (!response.ok) throw new Error(`capture failed: ${response.status}`);
  return response.json();
}

async function postVisitEvent(payload, config) {
  const base = normalizeDaemonUrl(config.daemonUrl);
  const response = await fetch(`${base}/visit-events`, {
    method: 'POST',
    headers: authHeaders(config.apiToken),
    body: JSON.stringify(payload),
    targetAddressSpace: 'loopback'
  });
  if (!response.ok) throw new Error(`visit event failed: ${response.status}`);
  return response.json();
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

function mediaFetchSupported(sourceUrl) {
  try {
    const url = new URL(sourceUrl);
    return ['http:', 'https:', 'data:'].includes(url.protocol);
  } catch (_) {
    return false;
  }
}

async function postMediaArtifact(payload, config) {
  const base = normalizeDaemonUrl(config.daemonUrl);
  const response = await fetch(`${base}/media-artifacts`, {
    method: 'POST',
    headers: authHeaders(config.apiToken),
    body: JSON.stringify(payload),
    targetAddressSpace: 'loopback'
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`media artifact failed: ${response.status} ${JSON.stringify(body)}`);
  return body;
}

async function buildMediaArtifactPayload(ref, capturePayload, captureResult) {
  const sourceUrl = String(ref.source_url || ref.sourceUrl || ref.src || '');
  const basePayload = {
    document_id: captureResult.document_id,
    snapshot_id: captureResult.snapshot_id,
    visit_id: capturePayload.visit_id || captureResult.visit_id,
    page_url: capturePayload.url,
    media_type: ref.media_type || ref.mediaType || ref.type,
    role: ref.role || 'content',
    source_url: sourceUrl,
    alt_text: ref.alt_text || ref.altText || ref.alt || '',
    title: ref.title || '',
    mime_type: ref.mime_type || ref.mimeType || '',
    width: ref.width,
    height: ref.height,
    duration_seconds: ref.duration_seconds || ref.durationSeconds || ref.duration,
    metadata: ref.metadata || {}
  };
  if (!mediaFetchSupported(sourceUrl)) {
    return { ...basePayload, capture_status: 'skipped', status_reason: 'unsupported-media-url-scheme' };
  }
  const response = await fetch(sourceUrl, { credentials: 'include', redirect: 'follow' });
  if (!response.ok) {
    return { ...basePayload, capture_status: 'failed', status_reason: `fetch-status-${response.status}` };
  }
  const contentLength = Number(response.headers.get('content-length') || 0);
  if (contentLength > MAX_MEDIA_ARTIFACT_BYTES) {
    return { ...basePayload, capture_status: 'skipped', status_reason: 'media-too-large' };
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > MAX_MEDIA_ARTIFACT_BYTES) {
    return { ...basePayload, capture_status: 'skipped', status_reason: 'media-too-large' };
  }
  return {
    ...basePayload,
    mime_type: basePayload.mime_type || response.headers.get('content-type') || '',
    byte_size: buffer.byteLength,
    content_base64: arrayBufferToBase64(buffer)
  };
}

async function uploadMediaArtifacts(capturePayload, captureResult, config) {
  const refs = Array.isArray(capturePayload.media_artifacts) ? capturePayload.media_artifacts.slice(0, MAX_MEDIA_ARTIFACTS_PER_CAPTURE) : [];
  if (!refs.length || !captureResult || !captureResult.snapshot_id || !captureResult.document_id) return { attempted: 0, stored: 0 };
  const results = [];
  for (const ref of refs) {
    try {
      const mediaPayload = await buildMediaArtifactPayload(ref, capturePayload, captureResult);
      results.push(await postMediaArtifact(mediaPayload, config));
    } catch (error) {
      results.push({ ok: false, error: String(error.message || error), media_type: ref.media_type || ref.mediaType || ref.type, source_url: ref.source_url || ref.sourceUrl || ref.src || '' });
    }
  }
  const failed = results.filter((item) => item && item.ok === false);
  if (failed.length) {
    await chrome.storage.local.set({ lastMediaArtifactError: { at: nowIso(), failed: failed.slice(0, 5) } });
  } else {
    await chrome.storage.local.remove('lastMediaArtifactError');
  }
  return { attempted: refs.length, stored: results.filter((item) => item && item.stored).length, results };
}

async function drainQueue() {
  const config = await getConfig();
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  const queue = Array.from(config.captureQueue || []);
  const delivered = [];
  while (queue.length) {
    const item = queue[0];
    try {
      const captureResult = await postOne(item.payload, config);
      delivered.push(captureResult);
      uploadMediaArtifacts(item.payload, captureResult, config).catch((error) => {
        chrome.storage.local.set({ lastMediaArtifactError: { at: nowIso(), error: String(error.message || error) } });
      });
      queue.shift();
      await saveQueue(queue);
    } catch (error) {
      await saveQueue(queue);
      return { ok: false, delivered, remaining: queue.length, error: String(error.message || error) };
    }
  }
  return { ok: true, delivered, remaining: 0 };
}

async function drainVisitEventQueue() {
  const config = await getConfig();
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  const queue = Array.from(config.visitEventQueue || []);
  const delivered = [];
  while (queue.length) {
    const item = queue[0];
    try {
      delivered.push(await postVisitEvent(item.payload, config));
      queue.shift();
      await saveVisitEventQueue(queue);
    } catch (error) {
      await saveVisitEventQueue(queue);
      await chrome.storage.local.set({ lastVisitEventError: { error: String(error.message || error), payload: item.payload, at: nowIso() } });
      return { ok: false, delivered, remaining: queue.length, error: String(error.message || error) };
    }
  }
  return { ok: true, delivered, remaining: 0 };
}

async function drainAllQueues() {
  const captures = await drainQueue();
  const visitEvents = await drainVisitEventQueue();
  return { captures, visitEvents };
}

async function enqueueCapture(payload) {
  const config = await getConfig();
  if (payload.is_incognito && !allowsIncognito(config.policyMode)) return { skipped: true, reason: 'incognito' };
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  const queue = Array.from(config.captureQueue || []);
  queue.push({ payload, queued_at: nowIso() });
  await saveQueue(queue);
  return drainQueue();
}

async function enqueueVisitEvent(payload) {
  const config = await getConfig();
  if (payload.is_incognito && !allowsIncognito(config.policyMode)) return { skipped: true, reason: 'incognito' };
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  if (!isTrackableUrl(payload.url, config.policyMode)) return { skipped: true, reason: 'blocked-url' };
  try {
    const delivered = await postVisitEvent(payload, config);
    await chrome.storage.local.remove('lastVisitEventError');
    await drainVisitEventQueue();
    return { ok: true, delivered: [delivered], remaining: 0 };
  } catch (error) {
    const queue = Array.from((await getConfig()).visitEventQueue || []);
    queue.push({ payload, queued_at: nowIso() });
    await saveVisitEventQueue(queue);
    await chrome.storage.local.set({ lastVisitEventError: { error: String(error.message || error), payload, at: nowIso() } });
    return { ok: false, delivered: [], remaining: queue.length, error: String(error.message || error) };
  }
}

async function emitVisitEventForState(state, eventType, endedAt = nowIso()) {
  const config = await getConfig();
  if (!state || !state.url || !state.visitId || !isTrackableUrl(state.url, config.policyMode)) {
    return { skipped: true, reason: 'missing-state' };
  }
  const segmentStartedAt = state.activeStartedAt || state.visitStartedAt || endedAt;
  const activeSeconds = state.activeStartedAt ? secondsBetween(state.activeStartedAt, endedAt) : 0;
  const payload = {
    event_id: stableVisitEventId(state, eventType, segmentStartedAt),
    visit_id: state.visitId,
    url: state.url,
    event_type: eventType,
    event_started_at: segmentStartedAt,
    event_ended_at: endedAt,
    active_seconds: activeSeconds,
    max_scroll_percent: sanitizedScrollPercent(state.maxScrollPercent),
    metadata: { tab_id: state.tabId }
  };
  return enqueueVisitEvent(payload);
}

async function finishActiveSegmentsExcept(activeTabId, eventType = 'tab-deactivated') {
  const states = await getTabVisitState();
  const endedAt = nowIso();
  const deliveries = [];
  for (const [key, state] of Object.entries(states)) {
    if (String(activeTabId) === key || !state || !state.activeStartedAt) continue;
    const eventState = { ...state };
    deliveries.push(emitVisitEventForState(eventState, eventType, endedAt));
    state.activeStartedAt = null;
    states[key] = state;
  }
  await saveTabVisitState(states);
  return Promise.allSettled(deliveries);
}

async function finishTabVisit(tabId, eventType = 'tab-deactivated', { remove = false } = {}) {
  const key = String(tabId);
  const states = await getTabVisitState();
  const state = states[key];
  if (!state) return { skipped: true, reason: 'missing-state' };
  const result = await emitVisitEventForState(state, eventType, nowIso());
  if (remove) delete states[key];
  else {
    state.activeStartedAt = null;
    states[key] = state;
  }
  await saveTabVisitState(states);
  return result;
}

async function ensureVisitState(tabId, url) {
  const config = await getConfig();
  if (config.capturePaused || !config.apiToken || !isTrackableUrl(url, config.policyMode)) return null;
  const key = String(tabId);
  let states = await getTabVisitState();
  let state = states[key];
  if (state && state.url !== url) {
    await finishTabVisit(tabId, 'navigation-away', { remove: true });
    states = await getTabVisitState();
    state = null;
  }
  if (!state) {
    state = {
      tabId,
      url,
      visitId: randomId('visit'),
      visitStartedAt: nowIso(),
      activeStartedAt: null,
      maxScrollPercent: 0
    };
  }
  states[key] = state;
  await saveTabVisitState(states);
  return state;
}

async function markTabActive(tabId, url) {
  await finishActiveSegmentsExcept(tabId, 'tab-deactivated');
  const state = await ensureVisitState(tabId, url);
  if (!state) return { skipped: true, reason: 'untrackable-tab' };
  if (!state.activeStartedAt) state.activeStartedAt = nowIso();
  const states = await getTabVisitState();
  states[String(tabId)] = state;
  await saveTabVisitState(states);
  return { ok: true, visit_id: state.visitId };
}

async function updateStateFromPayload(tabId, payload) {
  const state = await ensureVisitState(tabId, payload.url);
  if (!state) return null;
  state.maxScrollPercent = Math.max(sanitizedScrollPercent(state.maxScrollPercent), sanitizedScrollPercent(payload.max_scroll_percent));
  const states = await getTabVisitState();
  states[String(tabId)] = state;
  await saveTabVisitState(states);
  return state;
}

async function decorateCapturePayload(payload, sender) {
  const config = await getConfig();
  const tab = sender && sender.tab ? sender.tab : null;
  const decorated = { ...payload, is_incognito: Boolean(tab && tab.incognito), policy_mode: normalizePolicyMode(config.policyMode) };
  if (!tab || typeof tab.id !== 'number' || !decorated.url || !isTrackableUrl(decorated.url, config.policyMode)) return decorated;
  const state = await updateStateFromPayload(tab.id, decorated);
  if (!state) return decorated;
  if (tab.active && !state.activeStartedAt) {
    state.activeStartedAt = state.visitStartedAt || nowIso();
    const states = await getTabVisitState();
    states[String(tab.id)] = state;
    await saveTabVisitState(states);
  }
  decorated.visit_id = state.visitId;
  decorated.visit_started_at = state.visitStartedAt;
  return decorated;
}

const injectedTabs = new Map();

async function maybeInjectCapture(tabId, tabUrl) {
  const config = await getConfig();
  if (config.capturePaused || !config.apiToken) return { skipped: true, reason: config.capturePaused ? 'paused' : 'missing-token' };
  if (!isTrackableUrl(tabUrl, config.policyMode)) return { skipped: true, reason: 'blocked-url' };
  if (injectedTabs.get(tabId) === tabUrl) return { skipped: true, reason: 'already-injected' };
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['src/extractor.js', 'src/content_script.js']
    });
    injectedTabs.set(tabId, tabUrl);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: String(error.message || error) };
  }
}

chrome.tabs.onUpdated?.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete') return;
  if (tab && tab.url && tab.active) markTabActive(tabId, tab.url);
  maybeInjectCapture(tabId, tab && tab.url);
});

chrome.tabs.onActivated?.addListener((activeInfo) => {
  chrome.tabs.get(activeInfo.tabId, (tab) => {
    if (chrome.runtime.lastError || !tab || !tab.url) {
      finishActiveSegmentsExcept(activeInfo.tabId, 'tab-deactivated');
      return;
    }
    markTabActive(activeInfo.tabId, tab.url);
    maybeInjectCapture(activeInfo.tabId, tab.url);
  });
});

chrome.windows.onFocusChanged?.addListener((windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    finishActiveSegmentsExcept(null, 'window-blurred');
    return;
  }
  chrome.tabs.query({ active: true, windowId }, (tabs) => {
    const tab = tabs && tabs[0];
    if (chrome.runtime.lastError || !tab || typeof tab.id !== 'number' || !tab.url) {
      finishActiveSegmentsExcept(null, 'window-blurred');
      return;
    }
    markTabActive(tab.id, tab.url);
  });
});

chrome.tabs.onRemoved?.addListener((tabId) => {
  injectedTabs.delete(tabId);
  finishTabVisit(tabId, 'tab-closed', { remove: true });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== 'BMD_CAPTURE') return false;
  decorateCapturePayload(message.payload || {}, sender)
    .then((payload) => enqueueCapture(payload))
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
  return true;
});

chrome.runtime.onStartup?.addListener(() => { drainAllQueues(); });
chrome.runtime.onInstalled?.addListener(() => { drainAllQueues(); });
