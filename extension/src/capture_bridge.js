(function () {
function createCaptureBridge({
  chromeApi = globalThis.chrome,
  fetchImpl = globalThis.fetch,
  getConfig,
  allowsIncognito,
  isTrackableUrl,
  ensureCaptureIdentity,
  randomId,
  outboxApi,
  mediaQueueApi,
  mediaBridge,
  telemetry,
  normalizeDaemonUrl,
  authHeaders,
  nowIso = () => new Date().toISOString(),
  defaults = {},
  maxCaptureQueue = 100,
  maxLifecycleQueue = 200,
  maxMediaQueueTasks = 500,
  maxMediaQueueBlobBytes = 512 * 1024 * 1024,
  mediaTerminalTtlMs = 24 * 60 * 60 * 1000,
  staleClaimMs = 5 * 60 * 1000
} = {}) {
  if (![getConfig, allowsIncognito, isTrackableUrl, ensureCaptureIdentity, randomId, outboxApi, mediaQueueApi].every((item) => typeof item === 'function')) {
    throw new Error('capture bridge dependencies unavailable');
  }
  if (!mediaBridge || !telemetry) throw new Error('capture bridge collaborators unavailable');
  let readyPromise = null;

  async function saveQueue(queue) {
    if (queue.length > maxCaptureQueue) throw new Error('capture queue full');
    await chromeApi.storage.local.set({ captureQueue: queue });
  }

  async function saveVisitEventQueue(queue) {
    if (queue.length > maxLifecycleQueue) throw new Error('lifecycle queue full');
    await chromeApi.storage.local.set({ visitEventQueue: queue });
  }

  async function ensureOutboxReady() {
    const api = outboxApi();
    if (!api) {
      await telemetry.record('lastOutboxError', { at: nowIso(), error: 'indexeddb-outbox-unavailable', fallback: 'chrome.storage.local' });
      return null;
    }
    if (!readyPromise) {
      readyPromise = (async () => {
        const legacy = await chromeApi.storage.local.get({ captureQueue: [], visitEventQueue: [] });
        await api.importLegacyQueues(legacy);
        await chromeApi.storage.local.remove(['captureQueue', 'visitEventQueue']);
        await telemetry.remove('lastOutboxError');
        return api;
      })().catch(async (error) => {
        readyPromise = null;
        await telemetry.recordError('lastOutboxError', error, { fallback: 'chrome.storage.local' });
        return null;
      });
    }
    return readyPromise;
  }

  function nextAttemptAt(attempts) {
    const delayMs = Math.min(5 * 60 * 1000, 5_000 * (2 ** Math.max(0, Number(attempts || 1) - 1)));
    return new Date(Date.now() + delayMs).toISOString();
  }

  async function postCapture(payload, config) {
    const base = normalizeDaemonUrl(config.daemonUrl);
    const response = await fetchImpl(`${base}/capture`, {
      method: 'POST', headers: authHeaders(config.apiToken), body: JSON.stringify(payload), targetAddressSpace: 'loopback'
    });
    if (!response.ok) throw new Error(`capture failed: ${response.status}`);
    return response.json();
  }

  async function postVisitEvent(payload, config) {
    const base = normalizeDaemonUrl(config.daemonUrl);
    const response = await fetchImpl(`${base}/visit-events`, {
      method: 'POST', headers: authHeaders(config.apiToken), body: JSON.stringify(payload), targetAddressSpace: 'loopback'
    });
    if (!response.ok) throw new Error(`visit event failed: ${response.status}`);
    return response.json();
  }

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
          captureResult = await postCapture(item.payload, config);
          item.capture_result = captureResult;
          queue[0] = item;
          await saveQueue(queue);
        }
        delivered.push(captureResult);
        if (!item.media_enqueued && !item.mediaEnqueued) {
          try {
            await mediaBridge.queueMediaArtifacts(item.payload, captureResult);
            item.media_enqueued = true;
            queue[0] = item;
            await saveQueue(queue);
          } catch (error) {
            await telemetry.recordError('lastMediaArtifactError', error, { phase: 'queue-media' });
            await saveQueue(queue);
            return { ok: false, delivered, remaining: queue.length, error: telemetry.safeError(error), phase: 'queue-media' };
          }
        }
        queue.shift();
        await saveQueue(queue);
        mediaBridge.scheduleMediaDrain();
      } catch (error) {
        await saveQueue(queue);
        return { ok: false, delivered, remaining: queue.length, error: telemetry.safeError(error) };
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
        await telemetry.recordError('lastVisitEventError', error);
        return { ok: false, delivered, remaining: queue.length, error: telemetry.safeError(error) };
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
      await telemetry.remove('lastVisitEventError');
      await drainLegacyVisitEventQueue();
      return { ok: true, delivered: [delivered], remaining: 0 };
    } catch (error) {
      const queue = Array.from((await getConfig()).visitEventQueue || []);
      queue.push({ payload, queued_at: nowIso() });
      await saveVisitEventQueue(queue);
      await telemetry.recordError('lastVisitEventError', error);
      return { ok: false, delivered: [], remaining: queue.length, error: telemetry.safeError(error) };
    }
  }

  function byteLimit(config, kind) {
    const key = kind === 'capture' ? 'captureOutboxMaxBytes' : 'lifecycleOutboxMaxBytes';
    const configured = Number(config[key]);
    return Number.isFinite(configured) && configured > 0 ? Math.floor(configured) : defaults[key];
  }

  async function status() {
    const api = await ensureOutboxReady();
    if (!api) return { available: false };
    const config = await getConfig();
    const [capture, lifecycle, media, stored] = await Promise.all([
      api.getStats('capture'), api.getStats('lifecycle'), mediaQueueApi().getMediaQueueStats(), telemetry.get({ lastOutboxOverflow: null })
    ]);
    return {
      available: true,
      capture: { ...capture, max_items: maxCaptureQueue, max_bytes: byteLimit(config, 'capture') },
      lifecycle: { ...lifecycle, max_items: maxLifecycleQueue, max_bytes: byteLimit(config, 'lifecycle') },
      media: { ...media, max_tasks: maxMediaQueueTasks, max_blob_bytes: maxMediaQueueBlobBytes, terminal_ttl_ms: mediaTerminalTtlMs },
      last_overflow: stored.lastOutboxOverflow
    };
  }

  async function drainCaptureOutbox(api, config) {
    const delivered = [];
    const claimToken = randomId('capture-claim');
    for (let processed = 0; processed < 25; processed += 1) {
      const [claimed] = await api.claim('capture', { claimToken, limit: 1, staleClaimMs });
      if (!claimed) break;
      let item = claimed;
      try {
        const identifiedPayload = ensureCaptureIdentity(item.payload);
        if (identifiedPayload.observation_id !== item.payload?.observation_id || identifiedPayload.navigation_id !== item.payload?.navigation_id) {
          item = await api.updateClaim(item.sequence_id, claimToken, { payload: identifiedPayload });
        }
        let captureResult = item.capture_result || null;
        if (!captureResult) {
          captureResult = await postCapture(item.payload, config);
          item = await api.updateClaim(item.sequence_id, claimToken, { capture_result: captureResult });
        }
        delivered.push(captureResult);
        if (!item.media_enqueued) {
          await mediaBridge.queueMediaArtifacts(item.payload, captureResult);
          item = await api.updateClaim(item.sequence_id, claimToken, { media_enqueued: true });
        }
        if (!await api.acknowledge(item.sequence_id, claimToken)) throw new Error('outbox acknowledgement lost claim');
        mediaBridge.scheduleMediaDrain();
      } catch (error) {
        await api.retry(item.sequence_id, claimToken, { error: telemetry.safeError(error), nextAttemptAt: nextAttemptAt(item.attempts) });
        const stats = await api.getStats('capture');
        await telemetry.recordError('lastCaptureOutboxError', error, { attempts: item.attempts });
        return { ok: false, delivered, remaining: stats.count, error: telemetry.safeError(error) };
      }
    }
    await telemetry.remove('lastCaptureOutboxError');
    const stats = await api.getStats('capture');
    return { ok: true, delivered, remaining: stats.count, serialized_bytes: stats.serialized_bytes };
  }

  async function drainLifecycleOutbox(api, config) {
    const delivered = [];
    const claimToken = randomId('lifecycle-claim');
    for (let processed = 0; processed < 25; processed += 1) {
      const [item] = await api.claim('lifecycle', { claimToken, limit: 1, staleClaimMs });
      if (!item) break;
      try {
        delivered.push(await postVisitEvent(item.payload, config));
        if (!await api.acknowledge(item.sequence_id, claimToken)) throw new Error('outbox acknowledgement lost claim');
      } catch (error) {
        await api.retry(item.sequence_id, claimToken, { error: telemetry.safeError(error), nextAttemptAt: nextAttemptAt(item.attempts) });
        const stats = await api.getStats('lifecycle');
        await telemetry.recordError('lastVisitEventError', error, { attempts: item.attempts });
        return { ok: false, delivered, remaining: stats.count, error: telemetry.safeError(error) };
      }
    }
    await telemetry.remove('lastVisitEventError');
    const stats = await api.getStats('lifecycle');
    return { ok: true, delivered, remaining: stats.count, serialized_bytes: stats.serialized_bytes };
  }

  async function drainCaptureQueue() {
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
    const captures = await drainCaptureQueue();
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
    const enqueued = await api.enqueue('capture', ensureCaptureIdentity(payload), { maxItems: maxCaptureQueue, maxBytes: byteLimit(config, 'capture') });
    if (!enqueued.accepted) {
      await telemetry.record('lastOutboxOverflow', { at: nowIso(), kind: 'capture', reason: enqueued.reason, count: enqueued.stats.count, serialized_bytes: enqueued.stats.serialized_bytes });
      return { ok: false, rejected: true, reason: enqueued.reason, remaining: enqueued.stats.count };
    }
    await telemetry.remove('lastOutboxOverflow');
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
    const enqueued = await api.enqueue('lifecycle', payload, { maxItems: maxLifecycleQueue, maxBytes: byteLimit(config, 'lifecycle') });
    if (!enqueued.accepted) {
      await telemetry.record('lastOutboxOverflow', { at: nowIso(), kind: 'lifecycle', reason: enqueued.reason, count: enqueued.stats.count, serialized_bytes: enqueued.stats.serialized_bytes });
      return { ok: false, rejected: true, reason: enqueued.reason, remaining: enqueued.stats.count };
    }
    await telemetry.remove('lastOutboxOverflow');
    return drainLifecycleOutbox(api, config);
  }

  return { ensureOutboxReady, postCapture, postVisitEvent, status, drainCaptureQueue, drainVisitEventQueue, drainAllQueues, enqueueCapture, enqueueVisitEvent };
}

const api = { createCaptureBridge };
globalThis.BrowserMemoryCaptureBridge = api;
if (typeof module !== 'undefined') module.exports = api;
})();
