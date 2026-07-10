try { importScripts('shared.js', 'extractor.js', 'config_store.js', 'outbox.js', 'media_queue.js', 'cdp_recorder.js', 'cdp_session.js', 'visit_tracker.js', 'injection.js'); } catch (_) {}

const MAX_CAPTURE_QUEUE = 100;
const MAX_VISIT_EVENT_QUEUE = 200;
const MAX_MEDIA_ARTIFACTS_PER_CAPTURE = 50;
const MAX_MEDIA_ARTIFACT_BYTES = 250_000_000;
const MAX_MEDIA_QUEUE_TASKS = 500;
const MAX_MEDIA_QUEUE_BLOB_BYTES = 512 * 1024 * 1024;
const MEDIA_TERMINAL_TTL_MS = 24 * 60 * 60 * 1000;
const OUTBOX_STALE_CLAIM_MS = 5 * 60 * 1000;
let outboxReadyPromise = null;

function nowIso() {
  return new Date().toISOString();
}

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

async function saveQueue(queue) {
  if (queue.length > MAX_CAPTURE_QUEUE) throw new Error('capture queue full');
  await chrome.storage.local.set({ captureQueue: queue });
}

async function saveVisitEventQueue(queue) {
  if (queue.length > MAX_VISIT_EVENT_QUEUE) throw new Error('lifecycle queue full');
  await chrome.storage.local.set({ visitEventQueue: queue });
}

function outboxApi() {
  return globalThis.BrowserMemoryOutbox || null;
}

async function ensureOutboxReady() {
  const api = outboxApi();
  if (!api) {
    await chrome.storage.local.set({
      lastOutboxError: { at: nowIso(), error: 'indexeddb-outbox-unavailable', fallback: 'chrome.storage.local' }
    });
    return null;
  }
  if (!outboxReadyPromise) {
    outboxReadyPromise = (async () => {
      const legacy = await chrome.storage.local.get({ captureQueue: [], visitEventQueue: [] });
      await api.importLegacyQueues(legacy);
      await chrome.storage.local.remove(['captureQueue', 'visitEventQueue']);
      await chrome.storage.local.remove('lastOutboxError');
      return api;
    })().catch(async (error) => {
      outboxReadyPromise = null;
      await chrome.storage.local.set({
        lastOutboxError: { at: nowIso(), error: String(error.message || error), fallback: 'chrome.storage.local' }
      });
      return null;
    });
  }
  return outboxReadyPromise;
}

function nextOutboxAttemptAt(attempts) {
  const delayMs = Math.min(5 * 60 * 1000, 5_000 * (2 ** Math.max(0, Number(attempts || 1) - 1)));
  return new Date(Date.now() + delayMs).toISOString();
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
    if (url.pathname.toLowerCase().endsWith('.m3u8')) return false;
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

async function fetchPendingMediaArtifacts(scope, config) {
  const base = normalizeDaemonUrl(config.daemonUrl);
  const response = await fetch(`${base}/media-artifacts/fetch-pending`, {
    method: 'POST',
    headers: authHeaders(config.apiToken),
    body: JSON.stringify(scope || {}),
    targetAddressSpace: 'loopback'
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`media fetch-pending failed: ${response.status} ${JSON.stringify(body)}`);
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
  const tasks = [];
  for (let i = 0; i < artifacts.length; i += 1) {
    const task = mediaTaskFromArtifact(artifacts[i], refs[i], capturePayload, captureResult);
    if (!task.artifact_id || !task.source_url || !mediaFetchSupported(task.source_url)) continue;
    tasks.push(task);
  }
  const admitted = await api.putMediaTasks(tasks, { maxItems: MAX_MEDIA_QUEUE_TASKS });
  if (!admitted.accepted) throw new Error(admitted.reason || 'media-task-quota');
  return { queued: admitted.written.length };
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
    const admitted = await api.putFetchedBlob(
      task.artifact_id,
      fetched.blob,
      { mime_type: fetched.mime_type, byte_size: fetched.blob.byteLength },
      { maxBlobBytes: MAX_MEDIA_ARTIFACT_BYTES, maxTotalBytes: MAX_MEDIA_QUEUE_BLOB_BYTES }
    );
    if (!admitted.accepted) throw new Error(admitted.reason || 'media-blob-quota');
    blobRecord = admitted.row;
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
    await api.cleanupTerminalMediaTasks({ ttlMs: MEDIA_TERMINAL_TTL_MS, limit: 50 });
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

const cdpSessionApi = globalThis.BrowserMemoryCdpSession;
const cdpSession = cdpSessionApi && chrome.debugger
  ? cdpSessionApi.createCdpSession({ chromeApi: chrome, configStore, nowIso })
  : null;
const cdpCaptureContextByTab = cdpSession?.captureContextByTab || new Map();
const cdpRecorderByTab = cdpSession?.recorderByTab || new Map();

function cdpApi() {
  return globalThis.BrowserMemoryCdpRecorder || null;
}

function cdpCommand(tabId, method, params = {}) {
  if (!cdpSession) return Promise.reject(new Error('CDP session unavailable'));
  return cdpSession.command(tabId, method, params);
}

function cdpAttach(tabId) {
  if (!cdpSession) return Promise.reject(new Error('CDP session unavailable'));
  return cdpSession.attachOrRecover(tabId);
}

function cdpDetach(tabId) {
  return cdpSession ? cdpSession.detach(tabId) : Promise.resolve();
}

function latestDeliveredCaptureResult(result) {
  const delivered = Array.isArray(result?.delivered) ? result.delivered : [];
  if (delivered.length) return delivered[delivered.length - 1];
  const capturesDelivered = Array.isArray(result?.captures?.delivered) ? result.captures.delivered : [];
  if (capturesDelivered.length) return capturesDelivered[capturesDelivered.length - 1];
  if (result?.document_id && result?.snapshot_id) return result;
  return null;
}

async function rememberCdpCaptureContext(sender, payload, result) {
  const tabId = sender?.tab?.id;
  const captureResult = latestDeliveredCaptureResult(result);
  if (typeof tabId !== 'number' || !captureResult?.document_id || !captureResult?.snapshot_id) return;
  const context = {
    document_id: captureResult.document_id,
    snapshot_id: captureResult.snapshot_id,
    visit_id: captureResult.visit_id || payload.visit_id || '',
    page_url: payload.url || sender.tab.url || '',
    captured_at: nowIso()
  };
  if (cdpSession) await cdpSession.rememberCaptureContext(tabId, context);
  else cdpCaptureContextByTab.set(tabId, context);
}

function trimCdpSeenSet(state) {
  if (!state || state.seen.size <= 500) return;
  state.seen = new Set(Array.from(state.seen).slice(-300));
}

async function ensureCdpRecorder(tabId, tabUrl) {
  const api = cdpApi();
  if (!api || !chrome.debugger?.attach || typeof tabId !== 'number') return { skipped: true, reason: 'cdp-unavailable' };
  if (cdpSession) {
    await cdpSession.ready();
    await cdpSession.clearCaptureContextIfUrlChanged(tabId, tabUrl);
  }
  const config = await getConfig();
  const domains = api.normalizeDomains(config.cdpRecorderDomains, api.DEFAULT_CDP_RECORDER_DOMAINS);
  const mediaHosts = api.normalizeDomains(config.cdpRecorderMediaHosts, api.DEFAULT_CDP_MEDIA_HOSTS);
  if (config.capturePaused || !config.apiToken || !config.cdpRecorderEnabled || !api.shouldRecordTabUrl(tabUrl, domains)) {
    if (cdpRecorderByTab.has(tabId)) {
      await cdpDetach(tabId);
      cdpRecorderByTab.delete(tabId);
    }
    return { skipped: true, reason: 'cdp-not-enabled-for-tab' };
  }
  let state = cdpRecorderByTab.get(tabId);
  if (state?.attached) {
    state.page_url = tabUrl || state.page_url;
    state.mediaHosts = mediaHosts;
    return { ok: true, attached: true, existing: true };
  }
  try {
    const attachment = await cdpAttach(tabId);
    await cdpCommand(tabId, 'Network.enable', {
      maxTotalBufferSize: MAX_MEDIA_ARTIFACT_BYTES * 2,
      maxResourceBufferSize: MAX_MEDIA_ARTIFACT_BYTES
    });
    state = { attached: true, page_url: tabUrl || '', mediaHosts, requests: new Map(), seen: new Set(), attached_at: nowIso(), last_manifest_backfill_at: 0 };
    cdpRecorderByTab.set(tabId, state);
    await chrome.storage.local.set({ lastCdpRecorderStatus: { at: nowIso(), tabId, attached: true, recovered: Boolean(attachment?.recovered), page_url: state.page_url } });
    return { ok: true, attached: true, recovered: Boolean(attachment?.recovered) };
  } catch (error) {
    await chrome.storage.local.set({ lastCdpRecorderError: { at: nowIso(), tabId, error: String(error.message || error), phase: 'attach' } });
    return { ok: false, error: String(error.message || error) };
  }
}

async function recordCdpMediaBody(tabId, requestId, candidate, encodedDataLength = 0) {
  const api = cdpApi();
  const state = cdpRecorderByTab.get(tabId);
  const context = cdpSession ? await cdpSession.getCaptureContext(tabId) : cdpCaptureContextByTab.get(tabId);
  if (!api || !state || !context) return { skipped: true, reason: 'missing-cdp-context' };
  if (state.seen.has(candidate.source_url)) return { skipped: true, reason: 'duplicate-cdp-url' };
  state.seen.add(candidate.source_url);
  trimCdpSeenSet(state);
  const config = await getConfig();
  if (config.capturePaused || !config.apiToken) return { skipped: true, reason: config.capturePaused ? 'paused' : 'missing-token' };
  const metadata = await postMediaArtifact(api.cdpMediaArtifactPayload(context, candidate), config);
  if (candidate.is_manifest) {
    const now = Date.now();
    if (now - Number(state.last_manifest_backfill_at || 0) > 10_000) {
      state.last_manifest_backfill_at = now;
      fetchPendingMediaArtifacts({ domain: 'video.twimg.com', document_id: context.document_id, snapshot_id: context.snapshot_id, limit: 5 }, config)
        .catch((error) => chrome.storage.local.set({ lastCdpRecorderError: { at: nowIso(), tabId, error: String(error.message || error), phase: 'manifest-backfill' } }));
    }
    return { artifact_id: metadata.artifact_id, referenced: true, manifest: true };
  }
  const safeLength = Number(encodedDataLength || candidate.encoded_data_length || 0);
  if (safeLength > MAX_MEDIA_ARTIFACT_BYTES) {
    await postMediaArtifact(api.cdpMediaArtifactPayload(context, candidate, { capture_status: 'referenced', status_reason: 'cdp-media-too-large' }), config);
    return { artifact_id: metadata.artifact_id, referenced: true, reason: 'cdp-media-too-large' };
  }
  const body = await cdpCommand(tabId, 'Network.getResponseBody', { requestId });
  if (body.base64Encoded && api.approxBase64Bytes(body.body) > MAX_MEDIA_ARTIFACT_BYTES) {
    await postMediaArtifact(api.cdpMediaArtifactPayload(context, candidate, { capture_status: 'referenced', status_reason: 'cdp-media-too-large' }), config);
    return { artifact_id: metadata.artifact_id, referenced: true, reason: 'cdp-media-too-large' };
  }
  const blob = api.cdpBodyToBlob(body, candidate.mime_type || 'video/mp4');
  if (blob.size > MAX_MEDIA_ARTIFACT_BYTES) {
    await postMediaArtifact(api.cdpMediaArtifactPayload(context, candidate, { capture_status: 'referenced', status_reason: 'cdp-media-too-large' }), config);
    return { artifact_id: metadata.artifact_id, referenced: true, reason: 'cdp-media-too-large' };
  }
  const task = {
    artifact_id: metadata.artifact_id,
    document_id: context.document_id,
    snapshot_id: context.snapshot_id,
    visit_id: context.visit_id || '',
    page_url: context.page_url || '',
    source_url: candidate.source_url,
    media_type: 'video',
    role: candidate.role || 'cdp-segment',
    mime_type: candidate.mime_type || 'video/mp4',
    metadata: { cdp_recorder: true }
  };
  return putMediaArtifactBlob(task, { blob, metadata: { mime_type: task.mime_type, byte_size: blob.size, cdp_recorder: true } }, config);
}

function handleCdpResponseReceived(source, params) {
  const tabId = source?.tabId;
  const state = cdpRecorderByTab.get(tabId);
  const api = cdpApi();
  if (!state || !api || !params?.requestId) return;
  const candidate = api.cdpMediaCandidate(params.response || {}, params.type || '', state.mediaHosts || api.DEFAULT_CDP_MEDIA_HOSTS);
  if (!candidate || state.seen.has(candidate.source_url)) return;
  state.requests.set(params.requestId, candidate);
}

function handleCdpLoadingFinished(source, params) {
  const tabId = source?.tabId;
  const state = cdpRecorderByTab.get(tabId);
  if (!state || !params?.requestId) return;
  const candidate = state.requests.get(params.requestId);
  if (!candidate) return;
  state.requests.delete(params.requestId);
  recordCdpMediaBody(tabId, params.requestId, candidate, params.encodedDataLength)
    .then((result) => chrome.storage.local.set({ lastCdpRecorderStatus: { at: nowIso(), tabId, result } }))
    .catch((error) => chrome.storage.local.set({ lastCdpRecorderError: { at: nowIso(), tabId, error: String(error.message || error), phase: 'record-body', source_url: candidate.source_url } }));
}

chrome.debugger?.onEvent?.addListener((source, method, params) => {
  if (method === 'Network.responseReceived') handleCdpResponseReceived(source, params || {});
  else if (method === 'Network.loadingFinished') handleCdpLoadingFinished(source, params || {});
  else if (method === 'Network.loadingFailed') cdpRecorderByTab.get(source?.tabId)?.requests?.delete(params?.requestId);
});

chrome.debugger?.onDetach?.addListener((source, reason) => {
  if (typeof source?.tabId === 'number') {
    cdpRecorderByTab.delete(source.tabId);
    chrome.storage.local.set({ lastCdpRecorderStatus: { at: nowIso(), tabId: source.tabId, detached: true, reason } });
  }
});

async function drainLegacyCaptureQueue() {
  const config = await getConfig();
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  const queue = Array.from(config.captureQueue || []);
  const delivered = [];
  while (queue.length) {
    const item = queue[0];
    try {
      const identifiedPayload = ensureCaptureIdentity(item.payload);
      if (identifiedPayload.observation_id !== item.payload?.observation_id || identifiedPayload.navigation_id !== item.payload?.navigation_id) {
        item.payload = identifiedPayload;
        queue[0] = item;
        await saveQueue(queue);
      }
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

async function drainLegacyVisitEventQueue() {
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

async function enqueueLegacyCapture(payload) {
  const config = await getConfig();
  if (payload.is_incognito && !allowsIncognito(config.policyMode)) return { skipped: true, reason: 'incognito' };
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  const queue = Array.from(config.captureQueue || []);
  queue.push({ payload: ensureCaptureIdentity(payload), queued_at: nowIso() });
  await saveQueue(queue);
  return drainLegacyCaptureQueue();
}

async function enqueueLegacyVisitEvent(payload) {
  const config = await getConfig();
  if (payload.is_incognito && !allowsIncognito(config.policyMode)) return { skipped: true, reason: 'incognito' };
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  if (!isTrackableUrl(payload.url, config.policyMode)) return { skipped: true, reason: 'blocked-url' };
  try {
    const delivered = await postVisitEvent(payload, config);
    await chrome.storage.local.remove('lastVisitEventError');
    await drainLegacyVisitEventQueue();
    return { ok: true, delivered: [delivered], remaining: 0 };
  } catch (error) {
    const queue = Array.from((await getConfig()).visitEventQueue || []);
    queue.push({ payload, queued_at: nowIso() });
    await saveVisitEventQueue(queue);
    await chrome.storage.local.set({ lastVisitEventError: { error: String(error.message || error), payload, at: nowIso() } });
    return { ok: false, delivered: [], remaining: queue.length, error: String(error.message || error) };
  }
}

function outboxByteLimit(config, kind) {
  const key = kind === 'capture' ? 'captureOutboxMaxBytes' : 'lifecycleOutboxMaxBytes';
  const configured = Number(config[key]);
  return Number.isFinite(configured) && configured > 0 ? Math.floor(configured) : DEFAULTS[key];
}

async function outboxStatus() {
  const api = await ensureOutboxReady();
  if (!api) return { available: false };
  const config = await getConfig();
  const [capture, lifecycle, media, telemetry] = await Promise.all([
    api.getStats('capture'),
    api.getStats('lifecycle'),
    mediaQueueApi().getMediaQueueStats(),
    chrome.storage.local.get({ lastOutboxOverflow: null })
  ]);
  return {
    available: true,
    capture: { ...capture, max_items: MAX_CAPTURE_QUEUE, max_bytes: outboxByteLimit(config, 'capture') },
    lifecycle: { ...lifecycle, max_items: MAX_VISIT_EVENT_QUEUE, max_bytes: outboxByteLimit(config, 'lifecycle') },
    media: { ...media, max_tasks: MAX_MEDIA_QUEUE_TASKS, max_blob_bytes: MAX_MEDIA_QUEUE_BLOB_BYTES, terminal_ttl_ms: MEDIA_TERMINAL_TTL_MS },
    last_overflow: telemetry.lastOutboxOverflow
  };
}

async function drainCaptureOutbox(api, config) {
  const delivered = [];
  const claimToken = randomId('capture-claim');
  for (let processed = 0; processed < 25; processed += 1) {
    const [claimed] = await api.claim('capture', { claimToken, limit: 1, staleClaimMs: OUTBOX_STALE_CLAIM_MS });
    if (!claimed) break;
    let item = claimed;
    try {
      const identifiedPayload = ensureCaptureIdentity(item.payload);
      if (identifiedPayload.observation_id !== item.payload?.observation_id || identifiedPayload.navigation_id !== item.payload?.navigation_id) {
        item = await api.updateClaim(item.sequence_id, claimToken, { payload: identifiedPayload });
      }
      let captureResult = item.capture_result || null;
      if (!captureResult) {
        captureResult = await postOne(item.payload, config);
        item = await api.updateClaim(item.sequence_id, claimToken, { capture_result: captureResult });
      }
      delivered.push(captureResult);
      if (!item.media_enqueued) {
        await queueMediaArtifacts(item.payload, captureResult);
        item = await api.updateClaim(item.sequence_id, claimToken, { media_enqueued: true });
      }
      if (!await api.acknowledge(item.sequence_id, claimToken)) throw new Error('outbox acknowledgement lost claim');
      scheduleMediaDrain();
    } catch (error) {
      await api.retry(item.sequence_id, claimToken, {
        error: String(error.message || error),
        nextAttemptAt: nextOutboxAttemptAt(item.attempts)
      });
      const stats = await api.getStats('capture');
      await chrome.storage.local.set({
        lastCaptureOutboxError: { at: nowIso(), error: String(error.message || error), attempts: item.attempts }
      });
      return { ok: false, delivered, remaining: stats.count, error: String(error.message || error) };
    }
  }
  await chrome.storage.local.remove('lastCaptureOutboxError');
  const stats = await api.getStats('capture');
  return { ok: true, delivered, remaining: stats.count, serialized_bytes: stats.serialized_bytes };
}

async function drainLifecycleOutbox(api, config) {
  const delivered = [];
  const claimToken = randomId('lifecycle-claim');
  for (let processed = 0; processed < 25; processed += 1) {
    const [item] = await api.claim('lifecycle', { claimToken, limit: 1, staleClaimMs: OUTBOX_STALE_CLAIM_MS });
    if (!item) break;
    try {
      delivered.push(await postVisitEvent(item.payload, config));
      if (!await api.acknowledge(item.sequence_id, claimToken)) throw new Error('outbox acknowledgement lost claim');
    } catch (error) {
      await api.retry(item.sequence_id, claimToken, {
        error: String(error.message || error),
        nextAttemptAt: nextOutboxAttemptAt(item.attempts)
      });
      const stats = await api.getStats('lifecycle');
      await chrome.storage.local.set({
        lastVisitEventError: { at: nowIso(), error: String(error.message || error), attempts: item.attempts }
      });
      return { ok: false, delivered, remaining: stats.count, error: String(error.message || error) };
    }
  }
  await chrome.storage.local.remove('lastVisitEventError');
  const stats = await api.getStats('lifecycle');
  return { ok: true, delivered, remaining: stats.count, serialized_bytes: stats.serialized_bytes };
}

async function drainQueue() {
  const api = await ensureOutboxReady();
  if (!api) return drainLegacyCaptureQueue();
  const config = await getConfig();
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  return drainCaptureOutbox(api, config);
}

async function drainVisitEventQueue() {
  const api = await ensureOutboxReady();
  if (!api) return drainLegacyVisitEventQueue();
  const config = await getConfig();
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  return drainLifecycleOutbox(api, config);
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
  const api = await ensureOutboxReady();
  if (!api) return enqueueLegacyCapture(payload);
  const enqueued = await api.enqueue('capture', ensureCaptureIdentity(payload), { maxItems: MAX_CAPTURE_QUEUE, maxBytes: outboxByteLimit(config, 'capture') });
  if (!enqueued.accepted) {
    await chrome.storage.local.set({
      lastOutboxOverflow: { at: nowIso(), kind: 'capture', reason: enqueued.reason, count: enqueued.stats.count, serialized_bytes: enqueued.stats.serialized_bytes }
    });
    return { ok: false, rejected: true, reason: enqueued.reason, remaining: enqueued.stats.count };
  }
  await chrome.storage.local.remove('lastOutboxOverflow');
  return drainCaptureOutbox(api, config);
}

async function enqueueVisitEvent(payload) {
  const config = await getConfig();
  if (payload.is_incognito && !allowsIncognito(config.policyMode)) return { skipped: true, reason: 'incognito' };
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  if (!isTrackableUrl(payload.url, config.policyMode)) return { skipped: true, reason: 'blocked-url' };
  const api = await ensureOutboxReady();
  if (!api) return enqueueLegacyVisitEvent(payload);
  const enqueued = await api.enqueue('lifecycle', payload, { maxItems: MAX_VISIT_EVENT_QUEUE, maxBytes: outboxByteLimit(config, 'lifecycle') });
  if (!enqueued.accepted) {
    await chrome.storage.local.set({
      lastOutboxOverflow: { at: nowIso(), kind: 'lifecycle', reason: enqueued.reason, count: enqueued.stats.count, serialized_bytes: enqueued.stats.serialized_bytes }
    });
    return { ok: false, rejected: true, reason: enqueued.reason, remaining: enqueued.stats.count };
  }
  await chrome.storage.local.remove('lastOutboxOverflow');
  return drainLifecycleOutbox(api, config);
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
  if (cdpSession) {
    cdpSession.clearCaptureContext(tabId)
      .catch((error) => chrome.storage.local.set({ lastCdpRecorderError: { at: nowIso(), tabId, error: String(error.message || error), phase: 'clear-context' } }));
  } else cdpCaptureContextByTab.delete(tabId);
  if (cdpRecorderByTab.has(tabId)) {
    cdpDetach(tabId).finally(() => cdpRecorderByTab.delete(tabId));
  }
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
    uploadInlineMediaBlobs(message.uploads || [])
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

chrome.runtime.onStartup?.addListener(() => { drainAllQueues(); scheduleMediaDrain(); bootstrapActiveTabs(); });
chrome.runtime.onInstalled?.addListener(() => { drainAllQueues(); scheduleMediaDrain(); bootstrapActiveTabs(); });
chrome.alarms?.onAlarm?.addListener((alarm) => {
  if (alarm && alarm.name === 'bmd-outbox-drain') drainAllQueues();
  if (alarm && alarm.name === 'bmd-media-drain') scheduleMediaDrain();
});
chrome.alarms?.create?.('bmd-outbox-drain', { periodInMinutes: 1 });
chrome.alarms?.create?.('bmd-media-drain', { periodInMinutes: 1 });
// MV3 worker evaluation is itself a recovery boundary; runtime.onStartup only
// covers browser startup, not ordinary worker suspension and rehydration.
bootstrapActiveTabs({ markActive: false });
