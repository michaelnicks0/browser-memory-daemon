(function () {
function mediaFetchSupported(sourceUrl) {
  try {
    const url = new URL(sourceUrl);
    if (url.pathname.toLowerCase().endsWith('.m3u8')) return false;
    return ['http:', 'https:', 'data:'].includes(url.protocol);
  } catch (_) {
    return false;
  }
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
  try { suffix = new URL(task.source_url || '').pathname.toLowerCase().split('.').pop() || ''; } catch (_) {}
  const bySuffix = {
    png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', gif: 'image/gif', svg: 'image/svg+xml', avif: 'image/avif',
    mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime'
  };
  if (bySuffix[suffix]) return bySuffix[suffix];
  if (task.media_type === 'image') return 'image/*';
  if (task.media_type === 'video') return 'video/*';
  return '';
}

function createMediaBridge({
  chromeApi = globalThis.chrome,
  fetchImpl = globalThis.fetch,
  getConfig,
  mediaQueueApi,
  normalizeDaemonUrl,
  authHeaders,
  telemetry = null,
  nowIso = () => new Date().toISOString(),
  maxArtifactsPerCapture = 50,
  maxArtifactBytes = 250_000_000,
  maxQueueTasks = 500,
  maxQueueBlobBytes = 512 * 1024 * 1024,
  terminalTtlMs = 24 * 60 * 60 * 1000
} = {}) {
  if (typeof getConfig !== 'function' || typeof mediaQueueApi !== 'function') throw new Error('media bridge dependencies unavailable');
  let drainInFlight = false;
  const recordTelemetry = (key, value) => telemetry
    ? telemetry.record(key, value)
    : chromeApi.storage.local.set({ [key]: value });

  function mediaBackoffMs(attempts) {
    return Math.min(60 * 60 * 1000, 30_000 * (2 ** Math.max(0, Number(attempts || 1) - 1)));
  }

  async function postMediaArtifact(payload, config) {
    const base = normalizeDaemonUrl(config.daemonUrl);
    const response = await fetchImpl(`${base}/media-artifacts`, {
      method: 'POST', headers: authHeaders(config.apiToken), body: JSON.stringify(payload), targetAddressSpace: 'loopback'
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`media artifact failed: ${response.status}`);
    return body;
  }

  async function fetchPendingMediaArtifacts(scope, config) {
    const base = normalizeDaemonUrl(config.daemonUrl);
    const response = await fetchImpl(`${base}/media-artifacts/fetch-pending`, {
      method: 'POST', headers: authHeaders(config.apiToken), body: JSON.stringify(scope || {}), targetAddressSpace: 'loopback'
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`media fetch-pending failed: ${response.status}`);
    return body;
  }

  async function queueMediaArtifacts(capturePayload, captureResult) {
    const refs = Array.isArray(capturePayload.media_artifacts) ? capturePayload.media_artifacts.slice(0, maxArtifactsPerCapture) : [];
    const artifacts = Array.isArray(captureResult.media_artifacts) ? captureResult.media_artifacts : [];
    if (!refs.length || !artifacts.length) return { queued: 0 };
    const tasks = [];
    for (let i = 0; i < artifacts.length; i += 1) {
      const task = mediaTaskFromArtifact(artifacts[i], refs[i], capturePayload, captureResult);
      if (!task.artifact_id || !task.source_url || !mediaFetchSupported(task.source_url)) continue;
      tasks.push(task);
    }
    const admitted = await mediaQueueApi().putMediaTasks(tasks, { maxItems: maxQueueTasks });
    if (!admitted.accepted) throw new Error(admitted.reason || 'media-task-quota');
    return { queued: admitted.written.length };
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
    const response = await fetchImpl(`${base}/media-artifacts/${encodeURIComponent(task.artifact_id)}/blob`, {
      method: 'PUT', headers, body: blobRecord.blob, targetAddressSpace: 'loopback'
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`media blob upload failed: ${response.status}`);
    return body;
  }

  async function blobFromBase64(contentBase64, mimeType = '') {
    const clean = String(contentBase64 || '').replace(/\s+/g, '');
    if (!clean) throw new Error('missing inline media content');
    const response = await fetchImpl(`data:${String(mimeType || 'application/octet-stream').split(';', 1)[0]};base64,${clean}`);
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
    if (byteSize > maxArtifactBytes) {
      await postMediaArtifact(baseMediaStatusPayload(task, 'skipped', 'media-too-large'), config);
      return { artifact_id: task.artifact_id, skipped: true, reason: 'media-too-large' };
    }
    const blob = await blobFromBase64(upload.content_base64 || upload.contentBase64, task.mime_type);
    if (blob.size > maxArtifactBytes) {
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
      try { results.push(await uploadInlineMediaBlob(upload, config)); }
      catch (error) { results.push({ artifact_id: upload && (upload.artifact_id || upload.artifactId), ok: false, error: String(error.message || error) }); }
    }
    await recordTelemetry('lastInlineMediaUpload', { at: nowIso(), results: results.slice(0, 20) });
    return { ok: true, uploaded: results.filter((item) => item && item.stored).length, results };
  }

  async function fetchMediaForTask(task) {
    if (!mediaFetchSupported(task.source_url)) return { skipped: true, reason: 'unsupported-media-url-scheme' };
    const response = await fetchImpl(task.source_url, { credentials: 'include', redirect: 'follow', cache: 'no-store' });
    if (!response.ok) return { failed: true, reason: `fetch-status-${response.status}` };
    const contentLength = Number(response.headers.get('content-length') || 0);
    if (contentLength > maxArtifactBytes) return { skipped: true, reason: 'media-too-large' };
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength > maxArtifactBytes) return { skipped: true, reason: 'media-too-large' };
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
      if (fetched.failed) throw new Error(fetched.reason);
      const admitted = await api.putFetchedBlob(task.artifact_id, fetched.blob, { mime_type: fetched.mime_type, byte_size: fetched.blob.byteLength }, { maxBlobBytes: maxArtifactBytes, maxTotalBytes: maxQueueBlobBytes });
      if (!admitted.accepted) throw new Error(admitted.reason || 'media-blob-quota');
      blobRecord = admitted.row;
    }
    await api.markMediaTask(task.artifact_id, { status: 'uploading', last_error: '' });
    const uploaded = await putMediaArtifactBlob(task, blobRecord, config);
    if (uploaded.stored || ['skipped', 'failed', 'expired'].includes(uploaded.capture_status)) await api.deleteMediaTask(task.artifact_id);
    else {
      const attempts = Number(task.attempts || 0) + 1;
      await api.markMediaTask(task.artifact_id, { status: 'retrying', attempts, last_error: uploaded.status_reason || uploaded.capture_status || 'not-stored', next_attempt_at: new Date(Date.now() + mediaBackoffMs(attempts)).toISOString() });
    }
    return uploaded;
  }

  async function drainMediaQueue(options = {}) {
    if (drainInFlight) return { skipped: true, reason: 'already-running' };
    drainInFlight = true;
    const started = Date.now();
    const budgetMs = options.budgetMs || 25_000;
    const limit = options.limit || 10;
    const config = await getConfig();
    const api = mediaQueueApi();
    const results = [];
    try {
      await api.cleanupTerminalMediaTasks({ ttlMs: terminalTtlMs, limit: 50 });
      if (config.capturePaused || !config.apiToken) return { skipped: true, reason: config.capturePaused ? 'paused' : 'missing-token' };
      const tasks = await api.getDueMediaTasks(limit, nowIso());
      for (const task of tasks) {
        if (Date.now() - started > budgetMs) break;
        try { results.push(await processMediaTask(task, config)); }
        catch (error) {
          const attempts = Number(task.attempts || 0) + 1;
          const maxAttempts = Number(task.max_attempts || 5);
          const terminal = attempts >= maxAttempts;
          const nextAttempt = terminal ? null : new Date(Date.now() + mediaBackoffMs(attempts)).toISOString();
          await api.markMediaTask(task.artifact_id, { status: terminal ? 'failed' : 'retrying', attempts, next_attempt_at: nextAttempt, last_error: String(error.message || error) });
          if (terminal) await postMediaArtifact(baseMediaStatusPayload(task, 'failed', String(error.message || error).slice(0, 160)), config).catch(() => null);
          results.push({ artifact_id: task.artifact_id, ok: false, error: String(error.message || error), terminal });
        }
      }
      const counts = await api.countMediaTasksByStatus();
      await recordTelemetry('lastMediaQueueDrain', { at: nowIso(), results: results.slice(0, 20), counts });
      return { ok: true, processed: results.length, results, counts };
    } finally { drainInFlight = false; }
  }

  function scheduleMediaDrain() {
    chromeApi.alarms?.create?.('bmd-media-drain', { periodInMinutes: 1 });
    drainMediaQueue().catch((error) => telemetry
      ? telemetry.recordError('lastMediaArtifactError', error)
      : recordTelemetry('lastMediaArtifactError', { at: nowIso(), error: String(error.message || error) }));
  }

  return { postMediaArtifact, fetchPendingMediaArtifacts, queueMediaArtifacts, putMediaArtifactBlob, uploadInlineMediaBlobs, fetchMediaForTask, processMediaTask, drainMediaQueue, scheduleMediaDrain };
}

const api = { mediaFetchSupported, mediaTaskFromArtifact, baseMediaStatusPayload, inferMimeForTask, createMediaBridge };
globalThis.BrowserMemoryMediaBridge = api;
if (typeof module !== 'undefined') module.exports = api;
})();
