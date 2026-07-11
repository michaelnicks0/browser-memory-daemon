(function () {
function createCdpSession({ chromeApi = globalThis.chrome, configStore, nowIso = () => new Date().toISOString() } = {}) {
  if (!chromeApi?.debugger) throw new Error('chrome.debugger unavailable');
  if (!configStore) throw new Error('config store required');
  const recorderByTab = new Map();
  const captureContextByTab = new Map();
  let readyPromise = null;
  let contextMutationPromise = Promise.resolve();

  function ready() {
    if (!readyPromise) {
      readyPromise = configStore.getCdpCaptureContexts().then((stored) => {
        for (const [key, value] of Object.entries(stored || {})) {
          const tabId = Number(key);
          if (Number.isInteger(tabId) && value && typeof value === 'object') captureContextByTab.set(tabId, value);
        }
        return true;
      }).catch((error) => {
        readyPromise = null;
        throw error;
      });
    }
    return readyPromise;
  }

  async function persistCaptureContexts() {
    const stored = {};
    for (const [tabId, context] of captureContextByTab.entries()) stored[String(tabId)] = context;
    await configStore.saveCdpCaptureContexts(stored);
  }

  function mutateCaptureContexts(mutation) {
    const operation = contextMutationPromise.then(async () => {
      await ready();
      const before = new Map(captureContextByTab);
      const outcome = mutation();
      try {
        if (outcome.changed) await persistCaptureContexts();
      } catch (error) {
        captureContextByTab.clear();
        for (const [tabId, context] of before.entries()) captureContextByTab.set(tabId, context);
        throw error;
      }
      return outcome.value;
    });
    contextMutationPromise = operation.catch(() => null);
    return operation;
  }

  function rememberCaptureContext(tabId, context) {
    return mutateCaptureContexts(() => {
      captureContextByTab.set(tabId, { ...context, persisted_at: nowIso() });
      return { changed: true, value: true };
    });
  }

  async function getCaptureContext(tabId) {
    await ready();
    await contextMutationPromise;
    return captureContextByTab.get(tabId) || null;
  }

  function clearCaptureContext(tabId) {
    return mutateCaptureContexts(() => {
      const changed = captureContextByTab.delete(tabId);
      return { changed, value: changed };
    });
  }

  function clearCaptureContextIfUrlChanged(tabId, tabUrl) {
    return mutateCaptureContexts(() => {
      const context = captureContextByTab.get(tabId);
      if (!context || !tabUrl || context.page_url === tabUrl) return { changed: false, value: false };
      const changed = captureContextByTab.delete(tabId);
      return { changed, value: changed };
    });
  }

  function target(tabId) {
    return { tabId };
  }

  function command(tabId, method, params = {}) {
    return new Promise((resolve, reject) => {
      try {
        chromeApi.debugger.sendCommand(target(tabId), method, params, (result) => {
          const lastError = chromeApi.runtime?.lastError;
          if (lastError) reject(new Error(lastError.message));
          else resolve(result || {});
        });
      } catch (error) {
        reject(error);
      }
    });
  }

  function attach(tabId) {
    return new Promise((resolve, reject) => {
      try {
        chromeApi.debugger.attach(target(tabId), '1.3', () => {
          const lastError = chromeApi.runtime?.lastError;
          if (lastError) reject(new Error(lastError.message));
          else resolve({ attached: true, recovered: false });
        });
      } catch (error) {
        reject(error);
      }
    });
  }

  function attachedTargets() {
    return new Promise((resolve) => {
      if (typeof chromeApi.debugger.getTargets !== 'function') return resolve([]);
      try {
        chromeApi.debugger.getTargets((targets) => resolve(Array.isArray(targets) ? targets : []));
      } catch (_) {
        resolve([]);
      }
    });
  }

  async function attachOrRecover(tabId) {
    try {
      return await attach(tabId);
    } catch (error) {
      const targets = await attachedTargets();
      if (targets.some((item) => Number(item.tabId) === tabId && item.attached)) return { attached: true, recovered: true };
      throw error;
    }
  }

  function detach(tabId) {
    return new Promise((resolve) => {
      try {
        chromeApi.debugger.detach(target(tabId), () => resolve());
      } catch (_) {
        resolve();
      }
    });
  }

  return {
    recorderByTab,
    captureContextByTab,
    ready,
    rememberCaptureContext,
    getCaptureContext,
    clearCaptureContext,
    clearCaptureContextIfUrlChanged,
    command,
    attachOrRecover,
    detach,
    attachedTargets
  };
}

function createCdpRecorderController({
  chromeApi = globalThis.chrome,
  session = null,
  recorderApi = null,
  getConfig,
  mediaBridge,
  telemetry,
  nowIso = () => new Date().toISOString(),
  maxArtifactBytes = 250_000_000
} = {}) {
  if (typeof getConfig !== 'function' || !mediaBridge || !telemetry) throw new Error('CDP recorder controller dependencies unavailable');
  const recorderByTab = session?.recorderByTab || new Map();
  const captureContextByTab = session?.captureContextByTab || new Map();

  function latestDeliveredCaptureResult(result) {
    const delivered = Array.isArray(result?.delivered) ? result.delivered : [];
    if (delivered.length) return delivered[delivered.length - 1];
    const capturesDelivered = Array.isArray(result?.captures?.delivered) ? result.captures.delivered : [];
    if (capturesDelivered.length) return capturesDelivered[capturesDelivered.length - 1];
    if (result?.document_id && result?.snapshot_id) return result;
    return null;
  }

  async function rememberCaptureContext(sender, payload, result) {
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
    if (session) await session.rememberCaptureContext(tabId, context);
    else captureContextByTab.set(tabId, context);
  }

  function trimSeenSet(state) {
    if (!state || state.seen.size <= 500) return;
    state.seen = new Set(Array.from(state.seen).slice(-300));
  }

  async function ensureRecorder(tabId, tabUrl) {
    if (!recorderApi || !chromeApi.debugger?.attach || typeof tabId !== 'number' || !session) return { skipped: true, reason: 'cdp-unavailable' };
    await session.ready();
    await session.clearCaptureContextIfUrlChanged(tabId, tabUrl);
    const config = await getConfig();
    const domains = recorderApi.normalizeDomains(config.cdpRecorderDomains, recorderApi.DEFAULT_CDP_RECORDER_DOMAINS);
    const mediaHosts = recorderApi.normalizeDomains(config.cdpRecorderMediaHosts, recorderApi.DEFAULT_CDP_MEDIA_HOSTS);
    if (config.capturePaused || !config.apiToken || !config.cdpRecorderEnabled || !recorderApi.shouldRecordTabUrl(tabUrl, domains)) {
      if (recorderByTab.has(tabId)) {
        await session.detach(tabId);
        recorderByTab.delete(tabId);
      }
      return { skipped: true, reason: 'cdp-not-enabled-for-tab' };
    }
    let state = recorderByTab.get(tabId);
    if (state?.attached) {
      state.page_url = tabUrl || state.page_url;
      state.mediaHosts = mediaHosts;
      return { ok: true, attached: true, existing: true };
    }
    try {
      const attachment = await session.attachOrRecover(tabId);
      await session.command(tabId, 'Network.enable', { maxTotalBufferSize: maxArtifactBytes * 2, maxResourceBufferSize: maxArtifactBytes });
      state = { attached: true, page_url: tabUrl || '', mediaHosts, requests: new Map(), seen: new Set(), attached_at: nowIso(), last_manifest_backfill_at: 0 };
      recorderByTab.set(tabId, state);
      await telemetry.record('lastCdpRecorderStatus', { at: nowIso(), tabId, attached: true, recovered: Boolean(attachment?.recovered) });
      return { ok: true, attached: true, recovered: Boolean(attachment?.recovered) };
    } catch (error) {
      await telemetry.recordError('lastCdpRecorderError', error, { tabId, phase: 'attach' });
      return { ok: false, error: telemetry.safeError(error) };
    }
  }

  async function recordMediaBody(tabId, requestId, candidate, encodedDataLength = 0) {
    const state = recorderByTab.get(tabId);
    const context = session ? await session.getCaptureContext(tabId) : captureContextByTab.get(tabId);
    if (!recorderApi || !state || !context) return { skipped: true, reason: 'missing-cdp-context' };
    if (state.seen.has(candidate.source_url)) return { skipped: true, reason: 'duplicate-cdp-url' };
    state.seen.add(candidate.source_url);
    trimSeenSet(state);
    const config = await getConfig();
    if (config.capturePaused || !config.apiToken) return { skipped: true, reason: config.capturePaused ? 'paused' : 'missing-token' };
    const metadata = await mediaBridge.postMediaArtifact(recorderApi.cdpMediaArtifactPayload(context, candidate), config);
    if (candidate.is_manifest) {
      const now = Date.now();
      if (now - Number(state.last_manifest_backfill_at || 0) > 10_000) {
        state.last_manifest_backfill_at = now;
        mediaBridge.fetchPendingMediaArtifacts({ domain: 'video.twimg.com', document_id: context.document_id, snapshot_id: context.snapshot_id, limit: 5 }, config)
          .catch((error) => telemetry.recordError('lastCdpRecorderError', error, { tabId, phase: 'manifest-backfill' }));
      }
      return { artifact_id: metadata.artifact_id, referenced: true, manifest: true };
    }
    const tooLargePayload = () => recorderApi.cdpMediaArtifactPayload(context, candidate, { capture_status: 'referenced', status_reason: 'cdp-media-too-large' });
    const safeLength = Number(encodedDataLength || candidate.encoded_data_length || 0);
    if (safeLength > maxArtifactBytes) {
      await mediaBridge.postMediaArtifact(tooLargePayload(), config);
      return { artifact_id: metadata.artifact_id, referenced: true, reason: 'cdp-media-too-large' };
    }
    const body = await session.command(tabId, 'Network.getResponseBody', { requestId });
    if (body.base64Encoded && recorderApi.approxBase64Bytes(body.body) > maxArtifactBytes) {
      await mediaBridge.postMediaArtifact(tooLargePayload(), config);
      return { artifact_id: metadata.artifact_id, referenced: true, reason: 'cdp-media-too-large' };
    }
    const blob = recorderApi.cdpBodyToBlob(body, candidate.mime_type || 'video/mp4');
    if (blob.size > maxArtifactBytes) {
      await mediaBridge.postMediaArtifact(tooLargePayload(), config);
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
    return mediaBridge.putMediaArtifactBlob(task, { blob, metadata: { mime_type: task.mime_type, byte_size: blob.size, cdp_recorder: true } }, config);
  }

  function handleEvent(source, method, params = {}) {
    const tabId = source?.tabId;
    const state = recorderByTab.get(tabId);
    if (!state || !recorderApi) return;
    if (method === 'Network.responseReceived') {
      if (!params.requestId) return;
      const candidate = recorderApi.cdpMediaCandidate(params.response || {}, params.type || '', state.mediaHosts || recorderApi.DEFAULT_CDP_MEDIA_HOSTS);
      if (candidate && !state.seen.has(candidate.source_url)) state.requests.set(params.requestId, candidate);
      return;
    }
    if (method === 'Network.loadingFailed') {
      state.requests.delete(params.requestId);
      return;
    }
    if (method !== 'Network.loadingFinished' || !params.requestId) return;
    const candidate = state.requests.get(params.requestId);
    if (!candidate) return;
    state.requests.delete(params.requestId);
    recordMediaBody(tabId, params.requestId, candidate, params.encodedDataLength)
      .then((result) => telemetry.record('lastCdpRecorderStatus', { at: nowIso(), tabId, result }))
      .catch((error) => telemetry.recordError('lastCdpRecorderError', error, { tabId, phase: 'record-body' }));
  }

  function handleDetach(source, reason) {
    if (typeof source?.tabId !== 'number') return;
    recorderByTab.delete(source.tabId);
    telemetry.record('lastCdpRecorderStatus', { at: nowIso(), tabId: source.tabId, detached: true, reason });
  }

  function removeTab(tabId) {
    const clear = session ? session.clearCaptureContext(tabId) : Promise.resolve(captureContextByTab.delete(tabId));
    clear.catch((error) => telemetry.recordError('lastCdpRecorderError', error, { tabId, phase: 'clear-context' }));
    if (recorderByTab.has(tabId) && session) session.detach(tabId).finally(() => recorderByTab.delete(tabId));
  }

  return { recorderByTab, captureContextByTab, latestDeliveredCaptureResult, rememberCaptureContext, ensureRecorder, recordMediaBody, handleEvent, handleDetach, removeTab };
}

const api = { createCdpSession, createCdpRecorderController };
globalThis.BrowserMemoryCdpSession = api;
if (typeof module !== 'undefined') module.exports = api;
})();
