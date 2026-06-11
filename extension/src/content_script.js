(function () {
  if (globalThis.__BMD_CONTENT_SCRIPT_INSTALLED) {
    if (typeof globalThis.__BMD_CAPTURE_NOW === 'function') {
      globalThis.__BMD_CAPTURE_NOW('reinjected');
    }
    return;
  }
  globalThis.__BMD_CONTENT_SCRIPT_INSTALLED = true;
  globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
  globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'installed' };
  globalThis.__BMD_LAST_CAPTURE_KEY = '';

  const DELAYED_CAPTURE_MS = [0, 1500, 5000];
  const DEFAULT_CAPTURE_CONFIG = { policyMode: 'all' };
  const MAX_INLINE_BLOB_UPLOAD_BYTES = 25_000_000;

  function normalizePolicyMode(policyMode) {
    if (typeof globalThis.normalizeBrowserMemoryPolicyMode === 'function') {
      return globalThis.normalizeBrowserMemoryPolicyMode(policyMode);
    }
    const mode = String(policyMode || 'all').toLowerCase();
    return ['all', 'recall', 'balanced', 'strict'].includes(mode) ? mode : 'all';
  }

  function extensionErrorMessage(error) {
    return String(error && error.message || error || '');
  }

  function isExtensionContextInvalidated(error) {
    return /Extension context invalidated/i.test(extensionErrorMessage(error));
  }

  function safeRuntimeLastError() {
    try {
      return chrome.runtime.lastError ? chrome.runtime.lastError.message : '';
    } catch (error) {
      return extensionErrorMessage(error);
    }
  }

  function currentScrollPercent() {
    const element = document.documentElement || document.body;
    const scrollTop = globalThis.scrollY || element.scrollTop || 0;
    const scrollHeight = Math.max(element.scrollHeight || 0, document.body ? document.body.scrollHeight || 0 : 0);
    const viewportHeight = globalThis.innerHeight || element.clientHeight || 0;
    const denominator = Math.max(0, scrollHeight - viewportHeight);
    if (denominator <= 0) return 100;
    return Math.max(0, Math.min(100, Math.round((scrollTop / denominator) * 100)));
  }

  function updateMaxScrollPercent() {
    globalThis.__BMD_MAX_SCROLL_PERCENT = Math.max(globalThis.__BMD_MAX_SCROLL_PERCENT || 0, currentScrollPercent());
  }

  function captureKey(payload) {
    const text = String(payload.text || '');
    const media = Array.isArray(payload.media_artifacts) ? payload.media_artifacts : [];
    const mediaKey = media.map((item) => [item.media_type, item.role, item.source_url, item.width, item.height].join(':')).slice(0, 20).join('|');
    return [
      payload.url || '',
      payload.title || '',
      text.length,
      text.slice(0, 256),
      text.slice(-256),
      media.length,
      mediaKey
    ].join('\n');
  }

  function getCaptureConfig() {
    if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
      return Promise.resolve(DEFAULT_CAPTURE_CONFIG);
    }
    try {
      return Promise.resolve(chrome.storage.local.get(DEFAULT_CAPTURE_CONFIG))
        .then((cfg) => ({
          policyMode: normalizePolicyMode(cfg.policyMode)
        }))
        .catch((error) => {
          if (isExtensionContextInvalidated(error)) return DEFAULT_CAPTURE_CONFIG;
          throw error;
        });
    } catch (error) {
      if (isExtensionContextInvalidated(error)) return Promise.resolve(DEFAULT_CAPTURE_CONFIG);
      return Promise.reject(error);
    }
  }

  function latestCaptureResultFromResponse(response) {
    const delivered = response?.result?.delivered;
    if (Array.isArray(delivered) && delivered.length) return delivered[delivered.length - 1];
    if (response?.result?.media_artifacts) return response.result;
    return null;
  }

  function isBlobMediaRef(ref) {
    return /^blob:/i.test(String(ref?.source_url || ref?.sourceUrl || ''));
  }

  async function blobToBase64(blob) {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = '';
    const chunkSize = 0x8000;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
    }
    return btoa(binary);
  }

  async function buildBlobMediaUploads(payload, captureResult) {
    const refs = Array.isArray(payload.media_artifacts) ? payload.media_artifacts : [];
    const artifacts = Array.isArray(captureResult?.media_artifacts) ? captureResult.media_artifacts : [];
    const uploads = [];
    const failures = [];
    for (let i = 0; i < Math.min(refs.length, artifacts.length); i += 1) {
      const ref = refs[i];
      const artifact = artifacts[i];
      if (!isBlobMediaRef(ref) || !artifact?.artifact_id) continue;
      const sourceUrl = String(ref.source_url || ref.sourceUrl || '');
      const upload = {
        artifact_id: artifact.artifact_id,
        document_id: artifact.document_id || captureResult.document_id,
        snapshot_id: artifact.snapshot_id || captureResult.snapshot_id,
        visit_id: artifact.visit_id || captureResult.visit_id || payload.visit_id,
        page_url: artifact.page_url || payload.url || '',
        source_url: sourceUrl,
        media_type: artifact.media_type || ref.media_type || 'video',
        role: artifact.role || ref.role || 'content',
        mime_type: artifact.mime_type || ref.mime_type || '',
        width: artifact.width || ref.width,
        height: artifact.height || ref.height,
        duration_seconds: artifact.duration_seconds || ref.duration_seconds || ref.duration,
        metadata: { ...(ref.metadata || {}), inline_blob_upload: true }
      };
      try {
        const blobResponse = await fetch(sourceUrl);
        if (!blobResponse.ok) throw new Error(`blob-fetch-status-${blobResponse.status}`);
        const blob = await blobResponse.blob();
        upload.mime_type = blob.type || upload.mime_type;
        upload.byte_size = blob.size;
        if (blob.size <= MAX_INLINE_BLOB_UPLOAD_BYTES) {
          upload.content_base64 = await blobToBase64(blob);
        }
        uploads.push(upload);
      } catch (error) {
        failures.push({ artifact_id: artifact.artifact_id, source_url: sourceUrl, error: String(error && error.message || error) });
      }
    }
    return { uploads, failures };
  }

  function sendBlobMediaUploads(uploads) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: 'BMD_MEDIA_BLOB_UPLOADS', uploads }, (response) => {
          const lastError = safeRuntimeLastError();
          resolve({ response, lastError });
        });
      } catch (error) {
        resolve({ response: null, lastError: extensionErrorMessage(error) });
      }
    });
  }

  async function uploadBlobMediaRefs(payload, response) {
    const captureResult = latestCaptureResultFromResponse(response);
    if (!captureResult) return { skipped: true, reason: 'missing-capture-result' };
    const built = await buildBlobMediaUploads(payload, captureResult);
    if (!built.uploads.length) return { skipped: true, reason: 'no-blob-media', failures: built.failures };
    const uploadResult = await sendBlobMediaUploads(built.uploads);
    return { ...uploadResult, failures: built.failures, attempted: built.uploads.length };
  }

  function sendCapture(reason = 'scheduled') {
    if (globalThis.__BMD_CAPTURE_IN_PROGRESS) {
      globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'skipped', reason: 'capture-in-progress' };
      return;
    }
    if (typeof chrome === 'undefined' || !chrome.runtime) {
      globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'skipped', reason: 'missing-chrome-runtime' };
      return;
    }
    if (!globalThis.extractPageFromDocument) {
      globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'skipped', reason: 'missing-extractor' };
      return;
    }

    globalThis.__BMD_CAPTURE_IN_PROGRESS = true;
    getCaptureConfig().then((cfg) => {
      const policyMode = normalizePolicyMode(cfg.policyMode);
      const payload = {
        ...globalThis.extractPageFromDocument(document, { policyMode }),
        max_scroll_percent: globalThis.__BMD_MAX_SCROLL_PERCENT || 0
      };
      const textLength = payload.text ? payload.text.length : 0;
      if (!payload.text || (policyMode !== 'all' && textLength < 20)) {
        globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
        globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'skipped', reason: 'short-or-empty-text', captureReason: reason, textLength, blocked: Boolean(payload.blocked), url: payload.url, policyMode };
        return;
      }
      const key = captureKey(payload);
      if (key === globalThis.__BMD_LAST_CAPTURE_KEY) {
        globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
        globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'skipped', reason: 'duplicate-payload', captureReason: reason, textLength, url: payload.url, policyMode };
        return;
      }
      globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'sending', captureReason: reason, textLength, url: payload.url, policyMode };
      try {
        chrome.runtime.sendMessage({ type: 'BMD_CAPTURE', payload: { ...payload, capture_reason: reason, policy_mode: policyMode } }, (response) => {
          const lastError = safeRuntimeLastError();
          globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
          if (!lastError && response && response.ok) {
            globalThis.__BMD_LAST_CAPTURE_KEY = key;
            uploadBlobMediaRefs(payload, response)
              .then((mediaUpload) => { globalThis.__BMD_LAST_MEDIA_UPLOAD_STATUS = { at: new Date().toISOString(), ...mediaUpload }; })
              .catch((error) => { globalThis.__BMD_LAST_MEDIA_UPLOAD_STATUS = { at: new Date().toISOString(), error: extensionErrorMessage(error) }; });
          }
          globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'sent', ok: Boolean(response && response.ok), response, lastError, captureReason: reason, textLength, url: payload.url, policyMode };
        });
      } catch (error) {
        globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
        globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'error', error: extensionErrorMessage(error), captureReason: reason, textLength, url: payload.url, policyMode };
      }
    }).catch((error) => {
      globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
      globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'error', error: extensionErrorMessage(error), captureReason: reason };
    });
  }

  function scheduleCapture(reason, delays = DELAYED_CAPTURE_MS) {
    for (const delay of delays) {
      globalThis.setTimeout(() => sendCapture(reason), delay);
    }
  }

  function installSpaHooks() {
    if (globalThis.__BMD_SPA_HOOKS_INSTALLED) return;
    globalThis.__BMD_SPA_HOOKS_INSTALLED = true;
    const scheduleRouteCapture = (reason) => scheduleCapture(reason, [100, 1200, 3500]);
    for (const method of ['pushState', 'replaceState']) {
      const original = history[method];
      if (typeof original !== 'function') continue;
      history[method] = function (...args) {
        const result = original.apply(this, args);
        scheduleRouteCapture(`history.${method}`);
        return result;
      };
    }
    globalThis.addEventListener('popstate', () => scheduleRouteCapture('popstate'));
    globalThis.addEventListener('hashchange', () => scheduleRouteCapture('hashchange'));
  }

  globalThis.__BMD_CAPTURE_NOW = sendCapture;
  updateMaxScrollPercent();
  globalThis.addEventListener('scroll', updateMaxScrollPercent, { passive: true });
  globalThis.addEventListener('resize', updateMaxScrollPercent, { passive: true });
  installSpaHooks();
  scheduleCapture('initial');
})();
