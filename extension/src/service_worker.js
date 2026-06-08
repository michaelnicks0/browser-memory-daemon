try { importScripts('shared.js', 'extractor.js'); } catch (_) {}

const DEFAULTS = {
  daemonUrl: 'http://127.0.0.1:8765',
  apiToken: '',
  capturePaused: false,
  captureQueue: []
};

async function getConfig() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

async function saveQueue(queue) {
  await chrome.storage.local.set({ captureQueue: queue.slice(0, 100) });
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

async function drainQueue() {
  const config = await getConfig();
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  const queue = Array.from(config.captureQueue || []);
  const delivered = [];
  while (queue.length) {
    const item = queue[0];
    try {
      delivered.push(await postOne(item.payload, config));
      queue.shift();
      await saveQueue(queue);
    } catch (error) {
      await saveQueue(queue);
      return { ok: false, delivered, remaining: queue.length, error: String(error.message || error) };
    }
  }
  return { ok: true, delivered, remaining: 0 };
}

async function enqueueCapture(payload) {
  const config = await getConfig();
  if (payload.is_incognito) return { skipped: true, reason: 'incognito' };
  if (config.capturePaused) return { skipped: true, reason: 'paused' };
  if (!config.apiToken) return { skipped: true, reason: 'missing-token' };
  const queue = Array.from(config.captureQueue || []);
  queue.push({ payload, queued_at: new Date().toISOString() });
  await saveQueue(queue);
  return drainQueue();
}

const injectedTabs = new Map();

async function maybeInjectCapture(tabId, tabUrl) {
  const config = await getConfig();
  if (config.capturePaused || !config.apiToken) return { skipped: true, reason: config.capturePaused ? 'paused' : 'missing-token' };
  if (!tabUrl || (globalThis.shouldBlockBrowserMemoryUrl && globalThis.shouldBlockBrowserMemoryUrl(tabUrl))) {
    return { skipped: true, reason: 'blocked-url' };
  }
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
  maybeInjectCapture(tabId, tab.url);
});

chrome.tabs.onRemoved?.addListener((tabId) => { injectedTabs.delete(tabId); });

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== 'BMD_CAPTURE') return false;
  const payload = {
    ...message.payload,
    is_incognito: Boolean(sender && sender.tab && sender.tab.incognito)
  };
  enqueueCapture(payload)
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
  return true;
});

chrome.runtime.onStartup?.addListener(() => { drainQueue(); });
chrome.runtime.onInstalled?.addListener(() => { drainQueue(); });
