try { importScripts('shared.js', 'extractor.js', 'config_store.js', 'telemetry.js', 'outbox.js', 'media_queue.js', 'media_bridge.js', 'capture_bridge.js', 'cdp_recorder.js', 'cdp_session.js', 'visit_tracker.js', 'injection.js'); } catch (_) {}

const MAX_CAPTURE_QUEUE = 100;
const MAX_VISIT_EVENT_QUEUE = 200;
const MAX_MEDIA_ARTIFACTS_PER_CAPTURE = 50;
const MAX_MEDIA_ARTIFACT_BYTES = 250_000_000;
const MAX_MEDIA_QUEUE_TASKS = 500;
const MAX_MEDIA_QUEUE_BLOB_BYTES = 512 * 1024 * 1024;
const MEDIA_TERMINAL_TTL_MS = 24 * 60 * 60 * 1000;
const OUTBOX_STALE_CLAIM_MS = 5 * 60 * 1000;

function nowIso() {
  return new Date().toISOString();
}

const telemetryApi = globalThis.BrowserMemoryTelemetry;
if (!telemetryApi) throw new Error('telemetry module unavailable');
const telemetry = telemetryApi.createTelemetry({ chromeApi: chrome, nowIso });

function randomId(prefix = 'id') {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
    return `${prefix}_${globalThis.crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function ensureCaptureIdentity(payload) {
  const identified = { ...(payload || {}) };
  identified.observation_id = String(identified.observation_id || identified.observationId || '').trim() || randomId('observation');
  identified.navigation_id = String(identified.navigation_id || identified.navigationId || '').trim() || randomId('navigation');
  return identified;
}

const configStoreApi = globalThis.BrowserMemoryConfigStore;
if (!configStoreApi) throw new Error('config store module unavailable');
const configStore = configStoreApi.createConfigStore({ chromeApi: chrome, nowIso, normalizeImpl: globalThis.normalizeBrowserMemoryPolicyMode });
const DEFAULTS = configStore.DEFAULTS;

function normalizePolicyMode(policyMode) {
  return configStore.normalizePolicyMode(policyMode);
}

function allowsIncognito(policyMode) {
  return configStore.allowsIncognito(policyMode);
}

function isTrackableUrl(url, policyMode = 'all') {
  if (!url) return false;
  if (normalizePolicyMode(policyMode) === 'all') return true;
  return !(globalThis.shouldBlockBrowserMemoryUrl && globalThis.shouldBlockBrowserMemoryUrl(url, { policyMode }));
}

function getConfig() {
  return configStore.getConfig();
}

function mediaQueueApi() {
  const api = globalThis.BrowserMemoryMediaQueue;
  if (!api) throw new Error('media queue unavailable');
  return api;
}

const mediaBridgeApi = globalThis.BrowserMemoryMediaBridge;
if (!mediaBridgeApi) throw new Error('media bridge module unavailable');
const mediaBridge = mediaBridgeApi.createMediaBridge({
  chromeApi: chrome,
  fetchImpl: (...args) => fetch(...args),
  getConfig,
  mediaQueueApi,
  normalizeDaemonUrl,
  authHeaders,
  telemetry,
  nowIso,
  maxArtifactsPerCapture: MAX_MEDIA_ARTIFACTS_PER_CAPTURE,
  maxArtifactBytes: MAX_MEDIA_ARTIFACT_BYTES,
  maxQueueTasks: MAX_MEDIA_QUEUE_TASKS,
  maxQueueBlobBytes: MAX_MEDIA_QUEUE_BLOB_BYTES,
  terminalTtlMs: MEDIA_TERMINAL_TTL_MS
});

function drainMediaQueue(options = {}) {
  return mediaBridge.drainMediaQueue(options);
}

const cdpSessionApi = globalThis.BrowserMemoryCdpSession;
if (!cdpSessionApi) throw new Error('CDP session module unavailable');
const cdpSession = chrome.debugger
  ? cdpSessionApi.createCdpSession({ chromeApi: chrome, configStore, nowIso })
  : null;
const cdpRecorderController = cdpSessionApi.createCdpRecorderController({
  chromeApi: chrome,
  session: cdpSession,
  recorderApi: globalThis.BrowserMemoryCdpRecorder || null,
  getConfig,
  mediaBridge,
  telemetry,
  nowIso,
  maxArtifactBytes: MAX_MEDIA_ARTIFACT_BYTES
});

function ensureCdpRecorder(tabId, tabUrl) {
  return cdpRecorderController.ensureRecorder(tabId, tabUrl);
}

function rememberCdpCaptureContext(sender, payload, result) {
  return cdpRecorderController.rememberCaptureContext(sender, payload, result);
}

chrome.debugger?.onEvent?.addListener((source, method, params) => {
  cdpRecorderController.handleEvent(source, method, params || {});
});

chrome.debugger?.onDetach?.addListener((source, reason) => {
  cdpRecorderController.handleDetach(source, reason);
});

const captureBridgeApi = globalThis.BrowserMemoryCaptureBridge;
if (!captureBridgeApi) throw new Error('capture bridge module unavailable');
const captureBridge = captureBridgeApi.createCaptureBridge({
  chromeApi: chrome,
  fetchImpl: (...args) => fetch(...args),
  getConfig,
  allowsIncognito,
  isTrackableUrl,
  ensureCaptureIdentity,
  randomId,
  outboxApi: () => globalThis.BrowserMemoryOutbox || null,
  mediaQueueApi,
  mediaBridge,
  telemetry,
  normalizeDaemonUrl,
  authHeaders,
  nowIso,
  defaults: DEFAULTS,
  maxCaptureQueue: MAX_CAPTURE_QUEUE,
  maxLifecycleQueue: MAX_VISIT_EVENT_QUEUE,
  maxMediaQueueTasks: MAX_MEDIA_QUEUE_TASKS,
  maxMediaQueueBlobBytes: MAX_MEDIA_QUEUE_BLOB_BYTES,
  mediaTerminalTtlMs: MEDIA_TERMINAL_TTL_MS,
  staleClaimMs: OUTBOX_STALE_CLAIM_MS
});

function outboxStatus() {
  return captureBridge.status();
}

function drainQueue() {
  return captureBridge.drainCaptureQueue();
}

function drainVisitEventQueue() {
  return captureBridge.drainVisitEventQueue();
}

function drainAllQueues() {
  return captureBridge.drainAllQueues();
}

function enqueueCapture(payload) {
  return captureBridge.enqueueCapture(payload);
}

function enqueueVisitEvent(payload) {
  return captureBridge.enqueueVisitEvent(payload);
}

const visitTrackerApi = globalThis.BrowserMemoryVisitTracker;
if (!visitTrackerApi) throw new Error('visit tracker module unavailable');
const visitTracker = visitTrackerApi.createVisitTracker({ configStore, getConfig, isTrackableUrl, enqueueVisitEvent, ensureCaptureIdentity, randomId, nowIso });

function emitVisitEventForState(state, eventType, endedAt = nowIso()) {
  return visitTracker.emitVisitEventForState(state, eventType, endedAt);
}

function finishActiveSegmentsExcept(activeTabId, eventType = 'tab-deactivated') {
  return visitTracker.finishActiveSegmentsExcept(activeTabId, eventType);
}

function finishTabVisit(tabId, eventType = 'tab-deactivated', options = {}) {
  return visitTracker.finishTabVisit(tabId, eventType, options);
}

function markTabActive(tabId, url) {
  return visitTracker.markTabActive(tabId, url);
}

function decorateCapturePayload(payload, sender) {
  return visitTracker.decorateCapturePayload(payload, sender);
}

async function maybeInjectCapture(tabId, tabUrl) {
  return injectionController().maybeInjectCapture(tabId, tabUrl);
}

let injectionControllerInstance = null;
function injectionController() {
  if (!injectionControllerInstance) {
    const api = globalThis.BrowserMemoryInjection;
    if (!api) throw new Error('injection module unavailable');
    injectionControllerInstance = api.createInjectionController({ chromeApi: chrome, getConfig, isTrackableUrl, ensureCdpRecorder, markTabActive, nowIso });
  }
  return injectionControllerInstance;
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
  cdpRecorderController.removeTab(tabId);
  finishTabVisit(tabId, 'tab-closed', { remove: true });
});

function bootstrapActiveTabs(options) {
  injectionController().bootstrapActiveTabs(options);
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !message.type) return false;
  if (message.type === 'BMD_OUTBOX_STATUS') {
    outboxStatus()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
    return true;
  }
  if (message.type === 'BMD_MEDIA_BLOB_UPLOADS') {
    mediaBridge.uploadInlineMediaBlobs(message.uploads || [])
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
    return true;
  }
  if (message.type !== 'BMD_CAPTURE') return false;
  decorateCapturePayload(message.payload || {}, sender)
    .then((payload) => enqueueCapture(payload).then(async (result) => {
      await rememberCdpCaptureContext(sender, payload, result);
      return result;
    }))
    .then((result) => sendResponse({ ok: !result?.rejected, result }))
    .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
  return true;
});

chrome.runtime.onStartup?.addListener(() => { drainAllQueues(); mediaBridge.scheduleMediaDrain(); bootstrapActiveTabs(); });
chrome.runtime.onInstalled?.addListener(() => { drainAllQueues(); mediaBridge.scheduleMediaDrain(); bootstrapActiveTabs(); });
chrome.alarms?.onAlarm?.addListener((alarm) => {
  if (alarm && alarm.name === 'bmd-outbox-drain') drainAllQueues();
  if (alarm && alarm.name === 'bmd-media-drain') mediaBridge.scheduleMediaDrain();
});
chrome.alarms?.create?.('bmd-outbox-drain', { periodInMinutes: 1 });
chrome.alarms?.create?.('bmd-media-drain', { periodInMinutes: 1 });
// MV3 worker evaluation is itself a recovery boundary; runtime.onStartup only
// covers browser startup, not ordinary worker suspension and rehydration.
bootstrapActiveTabs({ markActive: false });
