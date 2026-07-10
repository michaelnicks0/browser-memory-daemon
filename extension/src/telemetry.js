(function () {
const SENSITIVE_FIELDS = new Set(['url', 'text', 'body', 'content', 'payload', 'token', 'header', 'headers']);
const URL_VALUE = /(?:https?|file):\/\/[^\s"']+|data:[^\s"']+/gi;

function isSensitiveKey(key) {
  const normalized = String(key).replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
  return normalized.split('_').some((part) => SENSITIVE_FIELDS.has(part));
}

function safeError(error, limit = 200) {
  return String(error?.message || error || '')
    .replace(URL_VALUE, '[redacted-url]')
    .slice(0, limit);
}

function sanitize(value, depth = 0) {
  if (depth > 5) return '[truncated]';
  if (value === null || value === undefined || typeof value === 'boolean' || typeof value === 'number') return value;
  if (typeof value === 'string') return value.replace(URL_VALUE, '[redacted-url]').slice(0, 500);
  if (Array.isArray(value)) return value.slice(0, 50).map((item) => sanitize(item, depth + 1));
  if (typeof value !== 'object') return String(value).slice(0, 200);
  const clean = {};
  for (const [key, item] of Object.entries(value)) {
    if (isSensitiveKey(key)) continue;
    clean[key] = sanitize(item, depth + 1);
  }
  return clean;
}

function createTelemetry({ chromeApi = globalThis.chrome, nowIso = () => new Date().toISOString() } = {}) {
  if (!chromeApi?.storage?.local) throw new Error('telemetry storage unavailable');

  async function record(key, value) {
    await chromeApi.storage.local.set({ [key]: sanitize(value) });
  }

  async function recordError(key, error, extra = {}) {
    await record(key, { at: nowIso(), ...extra, error: safeError(error) });
  }

  function remove(keys) {
    return chromeApi.storage.local.remove(keys);
  }

  function get(defaults) {
    return chromeApi.storage.local.get(defaults);
  }

  return { record, recordError, remove, get, sanitize, safeError };
}

const api = { safeError, sanitize, createTelemetry };
globalThis.BrowserMemoryTelemetry = api;
if (typeof module !== 'undefined') module.exports = api;
})();
