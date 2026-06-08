(function () {
  if (typeof chrome === 'undefined' || !chrome.runtime || !globalThis.extractPageFromDocument) return;
  const payload = globalThis.extractPageFromDocument(document);
  if (!payload.text || payload.text.length < 20) return;
  chrome.runtime.sendMessage({ type: 'BMD_CAPTURE', payload });
})();
