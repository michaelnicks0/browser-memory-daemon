(function () {
const DEFAULTS = Object.freeze({
  daemonUrl: 'http://127.0.0.1:8765',
  apiToken: '',
  capturePaused: false,
  policyMode: 'all',
  cdpRecorderEnabled: true,
  cdpRecorderDomains: ['x.com', 'twitter.com'],
  cdpRecorderMediaHosts: ['video.twimg.com'],
  captureOutboxMaxBytes: 32 * 1024 * 1024,
  lifecycleOutboxMaxBytes: 2 * 1024 * 1024,
  captureQueue: [],
  visitEventQueue: [],
  tabVisitState: {},
  cdpCaptureContextByTab: {}
});
const CDP_RECORDER_DEFAULT_ON_MIGRATION_KEY = 'cdpRecorderDefaultOnMigratedAt';

function normalizePolicyMode(policyMode, normalizeImpl = globalThis.normalizeBrowserMemoryPolicyMode) {
  if (typeof normalizeImpl === 'function') return normalizeImpl(policyMode);
  const mode = String(policyMode || 'all').toLowerCase();
  return ['all', 'recall', 'balanced', 'strict'].includes(mode) ? mode : 'all';
}

function createConfigStore({ chromeApi = globalThis.chrome, nowIso = () => new Date().toISOString(), normalizeImpl = globalThis.normalizeBrowserMemoryPolicyMode } = {}) {
  if (!chromeApi?.storage?.local) throw new Error('chrome.storage.local unavailable');
  return {
    DEFAULTS,
    normalizePolicyMode(value) {
      return normalizePolicyMode(value, normalizeImpl);
    },
    allowsIncognito(value) {
      return normalizePolicyMode(value, normalizeImpl) === 'all';
    },
    async getConfig() {
      const stored = await chromeApi.storage.local.get(DEFAULTS);
      if (!stored[CDP_RECORDER_DEFAULT_ON_MIGRATION_KEY]) {
        const migratedAt = nowIso();
        stored.cdpRecorderEnabled = true;
        stored[CDP_RECORDER_DEFAULT_ON_MIGRATION_KEY] = migratedAt;
        await chromeApi.storage.local.set({ cdpRecorderEnabled: true, [CDP_RECORDER_DEFAULT_ON_MIGRATION_KEY]: migratedAt });
      }
      return {
        ...DEFAULTS,
        ...stored,
        policyMode: normalizePolicyMode(stored.policyMode || DEFAULTS.policyMode, normalizeImpl),
        cdpRecorderEnabled: Boolean(stored.cdpRecorderEnabled)
      };
    },
    async getTabVisitState() {
      const stored = await chromeApi.storage.local.get({ tabVisitState: {} });
      return stored.tabVisitState && typeof stored.tabVisitState === 'object' ? stored.tabVisitState : {};
    },
    async saveTabVisitState(state) {
      await chromeApi.storage.local.set({ tabVisitState: state });
    },
    async getCdpCaptureContexts() {
      const stored = await chromeApi.storage.local.get({ cdpCaptureContextByTab: {} });
      return stored.cdpCaptureContextByTab && typeof stored.cdpCaptureContextByTab === 'object' ? stored.cdpCaptureContextByTab : {};
    },
    async saveCdpCaptureContexts(state) {
      await chromeApi.storage.local.set({ cdpCaptureContextByTab: state });
    }
  };
}

const api = { DEFAULTS, CDP_RECORDER_DEFAULT_ON_MIGRATION_KEY, normalizePolicyMode, createConfigStore };
globalThis.BrowserMemoryConfigStore = api;
if (typeof module !== 'undefined') module.exports = api;
})();
