(function () {
const CONTENT_SCRIPT_FILES = Object.freeze(['src/extractor.js', 'src/capture_digest.js', 'src/content_script.js']);

function createInjectionController({ chromeApi = globalThis.chrome, getConfig, isTrackableUrl, ensureCdpRecorder, markTabActive, nowIso = () => new Date().toISOString() } = {}) {
  if (!chromeApi?.scripting?.executeScript) throw new Error('chrome.scripting.executeScript unavailable');
  if (typeof getConfig !== 'function' || typeof isTrackableUrl !== 'function') throw new Error('injection policy dependencies unavailable');

  async function maybeInjectCapture(tabId, tabUrl) {
    const config = await getConfig();
    if (config.capturePaused || !config.apiToken) return { skipped: true, reason: config.capturePaused ? 'paused' : 'missing-token' };
    if (!isTrackableUrl(tabUrl, config.policyMode)) return { skipped: true, reason: 'blocked-url' };
    if (typeof ensureCdpRecorder === 'function') {
      ensureCdpRecorder(tabId, tabUrl).catch((error) => chromeApi.storage.local.set({
        lastCdpRecorderError: { at: nowIso(), tabId, error: String(error.message || error), phase: 'ensure' }
      }));
    }
    try {
      await chromeApi.scripting.executeScript({ target: { tabId }, files: CONTENT_SCRIPT_FILES.slice() });
      return { ok: true };
    } catch (error) {
      return { ok: false, error: String(error.message || error) };
    }
  }

  function bootstrapActiveTabs({ markActive = true } = {}) {
    chromeApi.tabs.query?.({ active: true }, (tabs) => {
      if (chromeApi.runtime.lastError || !Array.isArray(tabs)) return;
      for (const tab of tabs) {
        if (typeof tab.id !== 'number' || !tab.url) continue;
        if (markActive && typeof markTabActive === 'function') markTabActive(tab.id, tab.url);
        maybeInjectCapture(tab.id, tab.url);
      }
    });
  }

  return { maybeInjectCapture, bootstrapActiveTabs };
}

const api = { CONTENT_SCRIPT_FILES, createInjectionController };
globalThis.BrowserMemoryInjection = api;
if (typeof module !== 'undefined') module.exports = api;
})();
