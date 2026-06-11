try { importScripts('shared.js', 'extractor.js', 'media_queue.js'); } catch (_) {}

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

function mediaQueueApi() {
  const api = globalThis.BrowserMemoryMediaQueue;
  if (!api) throw new Error('media queue unavailable');
  return api;
}

function mediaBackoffMs(attempts) {
  return Math.min(60 * 60 * 1000, 30_000 * (2 ** Math.max(0, Number(attempts || 1) - 1)));
}

function mediaTaskFromArtifact(artifact, fallbackRef, capturePayload, captureResult) {
  const ref = fallbackRef || {};
  const sourceUrl = String(artifact.source_url || ref.source_url || ref.sourceUrl || ref.src || '');
  const metadata = artifact.metadata || ref.metadata || {};
  return {
    artifact_id: artifact.artifact_id || artifact.artifactId,
    document_id: artifact.document_id || captureResult.document_id,
    snapshot_id: artifact.snapshot_id || captureResult.snapshot_id,
    visit_id: artifact.visit_id || capturePayload.visit_id || captureResult.visit_id,
    page_url: artifact.page_url || capturePayload.url,
    source_url: sourceUrl,
    media_type: artifact.media_type || ref.media_type || ref.mediaType || ref.type,
    role: artifact.role || ref.role || 'content',
    mime_type: artifact.mime_type || ref.mime_type || ref.mimeType || '',
    width: artifact.width || ref.width,
    height: artifact.height || ref.height,
    duration_seconds: artifact.duration_seconds || ref.duration_seconds || ref.durationSeconds || ref.duration,
    priority: Number(metadata.priority || artifact.priority || ref.priority || 50),
    metadata,
    status: 'pending-fetch'
  };
}

async function queueMediaArtifacts(capturePayload, captureResult) {
  const refs = Array.isArray(capturePayload.media_artifacts) ? capturePayload.media_artifacts.slice(0, MAX_MEDIA_ARTIFACTS_PER_CAPTURE) : [];
  const artifacts = Array.isArray(captureResult.media_artifacts) ? captureResult.media_artifacts : [];
  if (!refs.length || !artifacts.length) return { queued: 0 };
  const api = mediaQueueApi();
  let queued = 0;
  for (let i = 0; i < artifacts.length; i += 1) {
    const task = mediaTaskFromArtifact(artifacts[i], refs[i], capturePayload, captureResult);
    if (!task.artifact_id || !task.source_url || !mediaFetchSupported(task.source_url)) continue;
    await api.putMediaTask(task);
    queued += 1;
  }
  return { queued };
}

function baseMediaStatusPayload(task, captureStatus, statusReason) {
  return {
    artifact_id: task.artifact_id,
    document_id: task.document_id,
    snapshot_id: task.snapshot_id,
    visit_id: task.visit_id,
    page_url: task.page_url,
    media_type: task.media_type,
    role: task.role || 'content',
    source_url: task.source_url,
    mime_type: task.mime_type || '',
    width: task.width,
    height: task.height,
    duration_seconds: task.duration_seconds,
    metadata: task.metadata || {},
    capture_status: captureStatus,
    status_reason: statusReason || ''
  };
}

function inferMimeForTask(task, fetchedMime = '') {
  const explicit = String(fetchedMime || task.mime_type || '').split(';', 1)[0].trim().toLowerCase();
  if (explicit && explicit !== 'application/octet-stream') return explicit;
  let suffix = '';
  try {
    suffix = new URL(task.source_url || '').pathname.toLowerCase().split('.').pop() || '';
  } catch (_) {}
  const bySuffix = {
    png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', gif: 'image/gif', svg: 'image/svg+xml', avif: 'image/avif',
    mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime'
  };
  if (bySuffix[suffix]) return bySuffix[suffix];
  if (task.media_type === 'image') return 'image/*';
  if (task.media_type === 'video') return 'video/*';
  return '';
}

async function putMediaArtifactBlob(task, blobRecord, config) {
  const base = normalizeDaemonUrl(config.daemonUrl);
  const metadata = blobRecord.metadata || {};
  const headers = {
    authorization: `Bearer ${config.apiToken}`,
    'x-bmd-document-id': task.document_id || '',
    'x-bmd-snapshot-id': task.snapshot_id || '',
    'x-bmd-source-url': task.source_url || ''
  };
  const uploadMime = inferMimeForTask(task, metadata.mime_type);
  if (uploadMime) headers['content-type'] = uploadMime;
  const response = await fetch(`${base}/media-artifacts/${encodeURIComponent(task.artifact_id)}/blob`, {
    method: 'PUT',
    headers,
    body: blobRecord.blob,
    targetAddressSpace: 'loopback'
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`media blob upload failed: ${response.status} ${JSON.stringify(body)}`);
  return body;
}

async function blobFromBase64(contentBase64, mimeType = '') {
  const clean = String(contentBase64 || '').replace(/\s+/g, '');
  if (!clean) throw new Error('missing inline media content');
  const response = await fetch(`data:${String(mimeType || 'application/octet-stream').split(';', 1)[0]};base64,${clean}`);
  if (!response.ok) throw new Error('inline media decode failed');
  return response.blob();
}

async function uploadInlineMediaBlob(upload, config) {
  const task = {
    artifact_id: upload.artifact_id || upload.artifactId,
    document_id: upload.document_id || upload.documentId,
    snapshot_id: upload.snapshot_id || upload.snapshotId,
    visit_id: upload.visit_id || upload.visitId,
    page_url: upload.page_url || upload.pageUrl || '',
    source_url: upload.source_url || upload.sourceUrl || '',
    media_type: upload.media_type || upload.mediaType || 'video',
    role: upload.role || 'content',
    mime_type: upload.mime_type || upload.mimeType || '',
    width: upload.width,
    height: upload.height,
    duration_seconds: upload.duration_seconds || upload.durationSeconds,
    metadata: upload.metadata || {}
  };
  if (!task.artifact_id) throw new Error('missing inline media artifact_id');
  const byteSize = Number(upload.byte_size || upload.byteSize || 0);
  if (byteSize > MAX_MEDIA_ARTIFACT_BYTES) {
    await postMediaArtifact(baseMediaStatusPayload(task, 'skipped', 'media-too-large'), config);
    return { artifact_id: task.artifact_id, skipped: true, reason: 'media-too-large' };
  }
  const blob = await blobFromBase64(upload.content_base64 || upload.contentBase64, task.mime_type);
  if (blob.size > MAX_MEDIA_ARTIFACT_BYTES) {
    await postMediaArtifact(baseMediaStatusPayload(task, 'skipped', 'media-too-large'), config);
    return { artifact_id: task.artifact_id, skipped: true, reason: 'media-too-large' };
  }
  return putMediaArtifactBlob(task, { blob, metadata: { mime_type: task.mime_type, byte_size: blob.size } }, config);
}

async function uploadInlineMediaBlobs(uploads) {
  const config = await getConfig();
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  const results = [];
  for (const upload of Array.isArray(uploads) ? uploads : []) {
    try {
      results.push(await uploadInlineMediaBlob(upload, config));
    } catch (error) {
      results.push({ artifact_id: upload && (upload.artifact_id || upload.artifactId), ok: false, error: String(error.message || error) });
    }
  }
  await chrome.storage.local.set({ lastInlineMediaUpload: { at: nowIso(), results: results.slice(0, 20) } });
  return { ok: true, uploaded: results.filter((item) => item && item.stored).length, results };
}

async function fetchMediaForTask(task) {
  if (!mediaFetchSupported(task.source_url)) {
    return { skipped: true, reason: 'unsupported-media-url-scheme' };
  }
  const response = await fetch(task.source_url, { credentials: 'include', redirect: 'follow', cache: 'no-store' });
  if (!response.ok) {
    return { failed: true, reason: `fetch-status-${response.status}` };
  }
  const contentLength = Number(response.headers.get('content-length') || 0);
  if (contentLength > MAX_MEDIA_ARTIFACT_BYTES) {
    return { skipped: true, reason: 'media-too-large' };
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > MAX_MEDIA_ARTIFACT_BYTES) {
    return { skipped: true, reason: 'media-too-large' };
  }
  return { blob: buffer, mime_type: response.headers.get('content-type') || task.mime_type || '' };
}

async function processMediaTask(task, config) {
  const api = mediaQueueApi();
  let blobRecord = await api.getFetchedBlob(task.artifact_id);
  if (!blobRecord) {
    await api.markMediaTask(task.artifact_id, { status: 'fetching', last_error: '' });
    const fetched = await fetchMediaForTask(task);
    if (fetched.skipped) {
      await postMediaArtifact(baseMediaStatusPayload(task, 'skipped', fetched.reason), config);
      await api.deleteMediaTask(task.artifact_id);
      return { artifact_id: task.artifact_id, skipped: true, reason: fetched.reason };
    }
    if (fetched.failed) {
      throw new Error(fetched.reason);
    }
    blobRecord = await api.putFetchedBlob(task.artifact_id, fetched.blob, { mime_type: fetched.mime_type, byte_size: fetched.blob.byteLength });
    await api.markMediaTask(task.artifact_id, { status: 'pending-upload', last_error: '' });
  }
  await api.markMediaTask(task.artifact_id, { status: 'uploading', last_error: '' });
  const uploaded = await putMediaArtifactBlob(task, blobRecord, config);
  if (uploaded.stored || ['skipped', 'failed', 'expired'].includes(uploaded.capture_status)) {
    await api.deleteMediaTask(task.artifact_id);
  } else {
    const attempts = Number(task.attempts || 0) + 1;
    await api.markMediaTask(task.artifact_id, { status: 'retrying', attempts, last_error: uploaded.status_reason || uploaded.capture_status || 'not-stored', next_attempt_at: new Date(Date.now() + mediaBackoffMs(attempts)).toISOString() });
  }
  return uploaded;
}

let mediaDrainInFlight = false;

async function drainMediaQueue(options = {}) {
  if (mediaDrainInFlight) return { skipped: true, reason: 'already-running' };
  mediaDrainInFlight = true;
  const started = Date.now();
  const budgetMs = options.budgetMs || 25_000;
  const limit = options.limit || 10;
  const config = await getConfig();
  const api = mediaQueueApi();
  const results = [];
  try {
    if (config.capturePaused || !config.apiToken) return { skipped: true, reason: config.capturePaused ? 'paused' : 'missing-token' };
    const tasks = await api.getDueMediaTasks(limit, nowIso());
    for (const task of tasks) {
      if (Date.now() - started > budgetMs) break;
      try {
        results.push(await processMediaTask(task, config));
      } catch (error) {
        const attempts = Number(task.attempts || 0) + 1;
        const maxAttempts = Number(task.max_attempts || 5);
        const terminal = attempts >= maxAttempts;
        const nextAttempt = terminal ? null : new Date(Date.now() + mediaBackoffMs(attempts)).toISOString();
        await api.markMediaTask(task.artifact_id, {
          status: terminal ? 'failed' : 'retrying',
          attempts,
          next_attempt_at: nextAttempt,
          last_error: String(error.message || error)
        });
        if (terminal) {
          await postMediaArtifact(baseMediaStatusPayload(task, 'failed', String(error.message || error).slice(0, 160)), config).catch(() => null);
        }
        results.push({ artifact_id: task.artifact_id, ok: false, error: String(error.message || error), terminal });
      }
    }
    const counts = await api.countMediaTasksByStatus();
    await chrome.storage.local.set({ lastMediaQueueDrain: { at: nowIso(), results: results.slice(0, 20), counts } });
    return { ok: true, processed: results.length, results, counts };
  } finally {
    mediaDrainInFlight = false;
  }
}

function scheduleMediaDrain() {
  if (chrome.alarms?.create) chrome.alarms.create('bmd-media-drain', { periodInMinutes: 1 });
  drainMediaQueue().catch((error) => chrome.storage.local.set({ lastMediaArtifactError: { at: nowIso(), error: String(error.message || error) } }));
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
      let captureResult = item.capture_result || item.captureResult || null;
      if (!captureResult) {
        captureResult = await postOne(item.payload, config);
        item.capture_result = captureResult;
        queue[0] = item;
        await saveQueue(queue);
      }
      delivered.push(captureResult);
      if (!item.media_enqueued && !item.mediaEnqueued) {
        try {
          await queueMediaArtifacts(item.payload, captureResult);
          item.media_enqueued = true;
          queue[0] = item;
          await saveQueue(queue);
        } catch (error) {
          await chrome.storage.local.set({ lastMediaArtifactError: { at: nowIso(), error: String(error.message || error), phase: 'queue-media' } });
          await saveQueue(queue);
          return { ok: false, delivered, remaining: queue.length, error: String(error.message || error), phase: 'queue-media' };
        }
      }
      queue.shift();
      await saveQueue(queue);
      scheduleMediaDrain();
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
  if (!message || !message.type) return false;
  if (message.type === 'BMD_MEDIA_BLOB_UPLOADS') {
    uploadInlineMediaBlobs(message.uploads || [])
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
    return true;
  }
  if (message.type !== 'BMD_CAPTURE') return false;
  decorateCapturePayload(message.payload || {}, sender)
    .then((payload) => enqueueCapture(payload))
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
  return true;
});

chrome.runtime.onStartup?.addListener(() => { drainAllQueues(); scheduleMediaDrain(); });
chrome.runtime.onInstalled?.addListener(() => { drainAllQueues(); scheduleMediaDrain(); });
chrome.alarms?.onAlarm?.addListener((alarm) => {
  if (alarm && alarm.name === 'bmd-media-drain') scheduleMediaDrain();
});
chrome.alarms?.create?.('bmd-media-drain', { periodInMinutes: 1 });
