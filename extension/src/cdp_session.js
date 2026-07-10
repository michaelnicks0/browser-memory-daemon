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

const api = { createCdpSession };
globalThis.BrowserMemoryCdpSession = api;
if (typeof module !== 'undefined') module.exports = api;
})();
