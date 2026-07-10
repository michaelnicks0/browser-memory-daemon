(function () {
const DB_NAME = 'browser-memory-outbox';
const DB_VERSION = 1;
const MESSAGE_STORE = 'messages';
const META_STORE = 'meta';
const LEGACY_IMPORT_KEY = 'legacy-chrome-storage-v1';
const DEFAULT_STALE_CLAIM_MS = 2 * 60 * 1000;
const VALID_KINDS = new Set(['capture', 'lifecycle']);

function nowIso() {
  return new Date().toISOString();
}

function serializedBytes(value) {
  const serialized = JSON.stringify(value ?? null);
  if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(serialized).byteLength;
  return unescape(encodeURIComponent(serialized)).length;
}

async function legacyImportKey(kind, item = {}) {
  const payload = item.payload || {};
  const stableId = kind === 'capture'
    ? String(payload.observation_id || payload.observationId || '')
    : String(payload.event_id || payload.eventId || '');
  if (stableId) return `${kind}:id:${stableId}`;
  const material = JSON.stringify([kind, item.queued_at || '', payload]);
  if (globalThis.crypto?.subtle) {
    const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(material));
    return `${kind}:sha256:${Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')}`;
  }
  return `${kind}:raw:${material}`;
}

async function prepareLegacyRows(kind, items) {
  const rows = [];
  for (const item of items) {
    rows.push({ ...normalizeLegacyItem(kind, item), legacy_key: await legacyImportKey(kind, item) });
  }
  return rows;
}

function normalizeKind(kind) {
  const normalized = String(kind || '').toLowerCase();
  if (!VALID_KINDS.has(normalized)) throw new Error(`unsupported outbox kind: ${normalized || 'empty'}`);
  return normalized;
}

function normalizeLegacyItem(kind, item = {}) {
  return {
    kind: normalizeKind(kind),
    payload: item.payload || {},
    capture_result: item.capture_result || item.captureResult || null,
    media_enqueued: Boolean(item.media_enqueued || item.mediaEnqueued),
    state: 'queued',
    claim_token: null,
    claimed_at: null,
    attempts: Number(item.attempts || 0),
    next_attempt_at: item.next_attempt_at || null,
    last_error: String(item.last_error || ''),
    queued_at: item.queued_at || nowIso(),
    updated_at: item.updated_at || item.queued_at || nowIso(),
    serialized_bytes: serializedBytes(item.payload || {})
  };
}

function requestToPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('indexeddb request failed'));
  });
}

function txComplete(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error || new Error('indexeddb transaction failed'));
    tx.onabort = () => reject(tx.error || new Error('indexeddb transaction aborted'));
  });
}

function openOutboxDb() {
  if (typeof indexedDB === 'undefined') return Promise.reject(new Error('indexedDB unavailable'));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(MESSAGE_STORE)) {
        const messages = db.createObjectStore(MESSAGE_STORE, { keyPath: 'sequence_id', autoIncrement: true });
        messages.createIndex('kind', 'kind', { unique: false });
        messages.createIndex('state', 'state', { unique: false });
        messages.createIndex('legacy_key', 'legacy_key', { unique: true });
      }
      if (!db.objectStoreNames.contains(META_STORE)) {
        db.createObjectStore(META_STORE, { keyPath: 'key' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('indexedDB open failed'));
  });
}

async function withTransaction(storeNames, mode, fn) {
  const db = await openOutboxDb();
  try {
    const tx = db.transaction(storeNames, mode);
    const stores = Object.fromEntries(storeNames.map((name) => [name, tx.objectStore(name)]));
    const value = await fn(stores);
    await txComplete(tx);
    return value;
  } finally {
    db.close();
  }
}

function statsFor(items, kind = null, now = nowIso()) {
  const filtered = kind ? items.filter((item) => item.kind === kind) : items;
  const oldest = filtered.reduce((value, item) => !value || item.queued_at < value ? item.queued_at : value, null);
  const oldestMs = Date.parse(oldest || '');
  const nowMs = Date.parse(now || '');
  return {
    count: filtered.length,
    serialized_bytes: filtered.reduce((total, item) => total + Number(item.serialized_bytes || 0), 0),
    claimed: filtered.filter((item) => item.state === 'claimed').length,
    oldest_queued_at: oldest,
    oldest_age_ms: Number.isFinite(oldestMs) && Number.isFinite(nowMs) ? Math.max(0, nowMs - oldestMs) : 0
  };
}

async function enqueue(kind, payload, { maxItems = null, queuedAt = nowIso() } = {}) {
  const normalizedKind = normalizeKind(kind);
  return withTransaction([MESSAGE_STORE], 'readwrite', async ({ messages }) => {
    const items = await requestToPromise(messages.getAll());
    const kindItems = items.filter((item) => item.kind === normalizedKind);
    if (maxItems !== null && kindItems.length >= Math.max(0, Number(maxItems) || 0)) {
      return { accepted: false, reason: 'queue-full', stats: statsFor(kindItems, normalizedKind, queuedAt) };
    }
    const row = normalizeLegacyItem(normalizedKind, { payload, queued_at: queuedAt });
    const sequenceId = await requestToPromise(messages.add(row));
    row.sequence_id = sequenceId;
    return { accepted: true, item: row, stats: statsFor([...kindItems, row], normalizedKind, queuedAt) };
  });
}

async function claim(kind, { limit = 1, claimToken, now = nowIso(), staleClaimMs = DEFAULT_STALE_CLAIM_MS } = {}) {
  const normalizedKind = normalizeKind(kind);
  if (!claimToken) throw new Error('claim token required');
  return withTransaction([MESSAGE_STORE], 'readwrite', async ({ messages }) => {
    const items = await requestToPromise(messages.getAll());
    const nowMs = Date.parse(now);
    const due = [];
    for (const item of items) {
      if (item.kind !== normalizedKind) continue;
      const claimedMs = Date.parse(item.claimed_at || '');
      if (item.state === 'claimed' && Number.isFinite(nowMs) && Number.isFinite(claimedMs) && nowMs - claimedMs >= staleClaimMs) {
        item.state = 'queued';
        item.claim_token = null;
        item.claimed_at = null;
        item.updated_at = now;
        await requestToPromise(messages.put(item));
      }
      if (item.state !== 'queued' || (item.next_attempt_at && item.next_attempt_at > now)) continue;
      due.push(item);
    }
    due.sort((a, b) => Number(a.sequence_id) - Number(b.sequence_id));
    const selected = due.slice(0, Math.max(1, Number(limit) || 1));
    for (const item of selected) {
      item.state = 'claimed';
      item.claim_token = claimToken;
      item.claimed_at = now;
      item.attempts = Number(item.attempts || 0) + 1;
      item.updated_at = now;
      await requestToPromise(messages.put(item));
    }
    return selected;
  });
}

async function updateClaim(sequenceId, claimToken, patch = {}, now = nowIso()) {
  return withTransaction([MESSAGE_STORE], 'readwrite', async ({ messages }) => {
    const item = await requestToPromise(messages.get(sequenceId));
    if (!item || item.state !== 'claimed' || item.claim_token !== claimToken) throw new Error('outbox claim lost');
    const updated = { ...item, ...patch, sequence_id: item.sequence_id, kind: item.kind, updated_at: now };
    if (patch.payload) updated.serialized_bytes = serializedBytes(patch.payload);
    await requestToPromise(messages.put(updated));
    return updated;
  });
}

async function acknowledge(sequenceId, claimToken) {
  return withTransaction([MESSAGE_STORE], 'readwrite', async ({ messages }) => {
    const item = await requestToPromise(messages.get(sequenceId));
    if (!item || item.state !== 'claimed' || item.claim_token !== claimToken) return false;
    await requestToPromise(messages.delete(sequenceId));
    return true;
  });
}

async function retry(sequenceId, claimToken, { error = '', nextAttemptAt = null, patch = {} } = {}, now = nowIso()) {
  return withTransaction([MESSAGE_STORE], 'readwrite', async ({ messages }) => {
    const item = await requestToPromise(messages.get(sequenceId));
    if (!item || item.state !== 'claimed' || item.claim_token !== claimToken) throw new Error('outbox claim lost');
    const updated = {
      ...item,
      ...patch,
      sequence_id: item.sequence_id,
      kind: item.kind,
      state: 'queued',
      claim_token: null,
      claimed_at: null,
      next_attempt_at: nextAttemptAt,
      last_error: String(error || ''),
      updated_at: now
    };
    if (patch.payload) updated.serialized_bytes = serializedBytes(patch.payload);
    await requestToPromise(messages.put(updated));
    return updated;
  });
}

async function getStats(kind = null, now = nowIso()) {
  const normalizedKind = kind === null ? null : normalizeKind(kind);
  return withTransaction([MESSAGE_STORE], 'readonly', async ({ messages }) => statsFor(await requestToPromise(messages.getAll()), normalizedKind, now));
}

async function list(kind = null) {
  const normalizedKind = kind === null ? null : normalizeKind(kind);
  return withTransaction([MESSAGE_STORE], 'readonly', async ({ messages }) => {
    const items = await requestToPromise(messages.getAll());
    return items.filter((item) => !normalizedKind || item.kind === normalizedKind).sort((a, b) => Number(a.sequence_id) - Number(b.sequence_id));
  });
}

async function importLegacyQueues({ captureQueue = [], visitEventQueue = [] } = {}) {
  const captures = Array.isArray(captureQueue) ? captureQueue : [];
  const lifecycle = Array.isArray(visitEventQueue) ? visitEventQueue : [];
  const prepared = [
    ...await prepareLegacyRows('capture', captures),
    ...await prepareLegacyRows('lifecycle', lifecycle)
  ];
  return withTransaction([MESSAGE_STORE, META_STORE], 'readwrite', async ({ messages, meta }) => {
    const existing = await requestToPromise(meta.get(LEGACY_IMPORT_KEY));
    const legacyIndex = messages.index('legacy_key');
    let imported = 0;
    for (const row of prepared) {
      if (await requestToPromise(legacyIndex.get(row.legacy_key))) continue;
      await requestToPromise(messages.add(row));
      imported += 1;
    }
    const value = {
      state: 'imported',
      captures: captures.length,
      lifecycle: lifecycle.length,
      imported,
      import_runs: Number(existing?.value?.import_runs || 0) + 1,
      imported_at: nowIso()
    };
    await requestToPromise(meta.put({ key: LEGACY_IMPORT_KEY, value }));
    return value;
  });
}

class MemoryOutboxStore {
  constructor() {
    this.items = new Map();
    this.meta = new Map();
    this.nextSequence = 1;
    this.writeChain = Promise.resolve();
  }
  _exclusive(fn) {
    const result = this.writeChain.then(fn, fn);
    this.writeChain = result.then(() => undefined, () => undefined);
    return result;
  }
  async enqueue(kind, payload, options = {}) {
    return this._exclusive(async () => {
      const normalizedKind = normalizeKind(kind);
      const kindItems = Array.from(this.items.values()).filter((item) => item.kind === normalizedKind);
      if (options.maxItems !== null && options.maxItems !== undefined && kindItems.length >= Math.max(0, Number(options.maxItems) || 0)) {
        return { accepted: false, reason: 'queue-full', stats: statsFor(kindItems, normalizedKind, options.queuedAt || nowIso()) };
      }
      const row = normalizeLegacyItem(normalizedKind, { payload, queued_at: options.queuedAt || nowIso() });
      row.sequence_id = this.nextSequence++;
      this.items.set(row.sequence_id, row);
      return { accepted: true, item: { ...row }, stats: statsFor([...kindItems, row], normalizedKind, options.queuedAt || nowIso()) };
    });
  }
  async claim(kind, options = {}) {
    return this._exclusive(async () => {
      const normalizedKind = normalizeKind(kind);
      if (!options.claimToken) throw new Error('claim token required');
      const at = options.now || nowIso();
      const atMs = Date.parse(at);
      const staleMs = options.staleClaimMs ?? DEFAULT_STALE_CLAIM_MS;
      const due = [];
      for (const item of this.items.values()) {
        if (item.kind !== normalizedKind) continue;
        const claimedMs = Date.parse(item.claimed_at || '');
        if (item.state === 'claimed' && Number.isFinite(atMs) && Number.isFinite(claimedMs) && atMs - claimedMs >= staleMs) {
          Object.assign(item, { state: 'queued', claim_token: null, claimed_at: null, updated_at: at });
        }
        if (item.state === 'queued' && (!item.next_attempt_at || item.next_attempt_at <= at)) due.push(item);
      }
      due.sort((a, b) => a.sequence_id - b.sequence_id);
      const selected = due.slice(0, Math.max(1, Number(options.limit) || 1));
      for (const item of selected) {
        Object.assign(item, { state: 'claimed', claim_token: options.claimToken, claimed_at: at, attempts: Number(item.attempts || 0) + 1, updated_at: at });
      }
      return selected.map((item) => ({ ...item }));
    });
  }
  async updateClaim(sequenceId, claimToken, patch = {}, now = nowIso()) {
    return this._exclusive(async () => {
      const item = this.items.get(sequenceId);
      if (!item || item.state !== 'claimed' || item.claim_token !== claimToken) throw new Error('outbox claim lost');
      Object.assign(item, patch, { sequence_id: item.sequence_id, kind: item.kind, updated_at: now });
      if (patch.payload) item.serialized_bytes = serializedBytes(patch.payload);
      return { ...item };
    });
  }
  async acknowledge(sequenceId, claimToken) {
    return this._exclusive(async () => {
      const item = this.items.get(sequenceId);
      if (!item || item.state !== 'claimed' || item.claim_token !== claimToken) return false;
      this.items.delete(sequenceId);
      return true;
    });
  }
  async retry(sequenceId, claimToken, options = {}, now = nowIso()) {
    return this._exclusive(async () => {
      const item = this.items.get(sequenceId);
      if (!item || item.state !== 'claimed' || item.claim_token !== claimToken) throw new Error('outbox claim lost');
      Object.assign(item, options.patch || {}, {
        sequence_id: item.sequence_id,
        kind: item.kind,
        state: 'queued',
        claim_token: null,
        claimed_at: null,
        next_attempt_at: options.nextAttemptAt || null,
        last_error: String(options.error || ''),
        updated_at: now
      });
      if (options.patch?.payload) item.serialized_bytes = serializedBytes(options.patch.payload);
      return { ...item };
    });
  }
  async getStats(kind = null, now = nowIso()) {
    await this.writeChain;
    const normalizedKind = kind === null ? null : normalizeKind(kind);
    return statsFor(Array.from(this.items.values()), normalizedKind, now);
  }
  async list(kind = null) {
    await this.writeChain;
    const normalizedKind = kind === null ? null : normalizeKind(kind);
    return Array.from(this.items.values()).filter((item) => !normalizedKind || item.kind === normalizedKind).sort((a, b) => a.sequence_id - b.sequence_id).map((item) => ({ ...item }));
  }
  async importLegacyQueues(queues = {}) {
    return this._exclusive(async () => {
      const captures = Array.isArray(queues.captureQueue) ? queues.captureQueue : [];
      const lifecycle = Array.isArray(queues.visitEventQueue) ? queues.visitEventQueue : [];
      const prepared = [
        ...await prepareLegacyRows('capture', captures),
        ...await prepareLegacyRows('lifecycle', lifecycle)
      ];
      const existingKeys = new Set(Array.from(this.items.values()).map((item) => item.legacy_key).filter(Boolean));
      let imported = 0;
      for (const row of prepared) {
        if (existingKeys.has(row.legacy_key)) continue;
        row.sequence_id = this.nextSequence++;
        this.items.set(row.sequence_id, row);
        existingKeys.add(row.legacy_key);
        imported += 1;
      }
      const existing = this.meta.get(LEGACY_IMPORT_KEY);
      const value = {
        state: 'imported',
        captures: captures.length,
        lifecycle: lifecycle.length,
        imported,
        import_runs: Number(existing?.import_runs || 0) + 1,
        imported_at: nowIso()
      };
      this.meta.set(LEGACY_IMPORT_KEY, value);
      return value;
    });
  }
}

const api = {
  openOutboxDb,
  enqueue,
  claim,
  updateClaim,
  acknowledge,
  retry,
  getStats,
  list,
  importLegacyQueues,
  MemoryOutboxStore,
  serializedBytes,
  statsFor
};

globalThis.BrowserMemoryOutbox = api;
if (typeof module !== 'undefined') module.exports = api;
})();
