(function () {
  if (globalThis.__BMD_CAPTURE_SENT || globalThis.__BMD_CAPTURE_IN_PROGRESS) return;
  globalThis.__BMD_CAPTURE_IN_PROGRESS = true;
  globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'started' };
  if (typeof chrome === 'undefined' || !chrome.runtime) {
    globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
    globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'skipped', reason: 'missing-chrome-runtime' };
    return;
  }
  if (!globalThis.extractPageFromDocument) {
    globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
    globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'skipped', reason: 'missing-extractor' };
    return;
  }
  const payload = globalThis.extractPageFromDocument(document);
  if (!payload.text || payload.text.length < 20) {
    globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
    globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'skipped', reason: 'short-or-empty-text', textLength: payload.text ? payload.text.length : 0, blocked: Boolean(payload.blocked), url: payload.url };
    return;
  }
  globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'sending', textLength: payload.text.length, url: payload.url };
  chrome.runtime.sendMessage({ type: 'BMD_CAPTURE', payload }, (response) => {
    const lastError = chrome.runtime.lastError ? chrome.runtime.lastError.message : '';
    globalThis.__BMD_CAPTURE_IN_PROGRESS = false;
    globalThis.__BMD_CAPTURE_SENT = !lastError && Boolean(response && response.ok);
    globalThis.__BMD_LAST_CAPTURE_STATUS = { stage: 'sent', ok: Boolean(response && response.ok), response, lastError, textLength: payload.text.length, url: payload.url };
  });
})();
