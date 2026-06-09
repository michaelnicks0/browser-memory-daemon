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

  function normalizePolicyMode(policyMode) {
    if (typeof globalThis.normalizeBrowserMemoryPolicyMode === 'function') {
      return globalThis.normalizeBrowserMemoryPolicyMode(policyMode);
    }
    const mode = String(policyMode || 'all').toLowerCase();
    return ['all', 'recall', 'balanced', 'strict'].includes(mode) ? mode : 'all';
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
    return [
      payload.url || '',
      payload.title || '',
      text.length,
      text.slice(0, 256),
      text.slice(-256)
    ].join('\n');
  }

  function getCaptureConfig() {
    if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
      return Promise.resolve(DEFAULT_CAPTURE_CONFIG);
    }
    return chrome.storage.local.get(DEFAULT_CAPTURE_CONFIG).then((cfg) => ({
      policyMode: normalizePolicyMode(cfg.policyMode)
    }));
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
      chrome.runtime.sendMessage({ type: 'BMD_CAPTURE', payload: { ...payload, capture_reason: reason, policy_mode: policyMode } }, (response) => {
        const lastError = chrome.runtime.lastError ? chrome.runtime.lastError.message : '';
        globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
        if (!lastError && response && response.ok) {
          globalThis.__BMD_LAST_CAPTURE_KEY = key;
        }
        globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'sent', ok: Boolean(response && response.ok), response, lastError, captureReason: reason, textLength, url: payload.url, policyMode };
      });
    }).catch((error) => {
      globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
      globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'error', error: String(error && error.message || error), captureReason: reason };
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
