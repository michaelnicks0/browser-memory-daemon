(function () {
const DB_NAME = 'browser-memory-media-v1';
const DB_VERSION = 2;
const TASK_STORE = 'tasks';
const BLOB_STORE = 'blobs';
const DEFAULT_MAX_ATTEMPTS = 5;
const PROCESSING_STALE_MS = 2 * 60 * 1000;
const DUE_STATUSES = new Set(['pending-fetch', 'pending-upload', 'retrying']);
const PROCESSING_STATUSES = new Set(['fetching', 'uploading']);
const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'skipped', 'expired', 'purged']);
const DEFAULT_TERMINAL_TTL_MS = 24 * 60 * 60 * 1000;

function nowIso() {
  return new Date().toISOString();
}

function normalizeTask(task = {}) {
  const at = nowIso();
  return {
    status: 'pending-fetch',
    attempts: 0,
    max_attempts: DEFAULT_MAX_ATTEMPTS,
    next_attempt_at: null,
    last_error: '',
    created_at: at,
    updated_at: at,
    ...task,
    artifact_id: String(task.artifact_id || task.artifactId || '')
  };
}

function mediaTaskIsDue(task, now = nowIso()) {
  const status = String(task.status || 'pending-fetch');
  if (DUE_STATUSES.has(status)) {
    return !task.next_attempt_at || task.next_attempt_at <= now;
  }
  if (PROCESSING_STATUSES.has(status)) {
    const updatedMs = Date.parse(task.updated_at || task.created_at || '');
    const nowMs = Date.parse(now || '');
    return Number.isFinite(updatedMs) && Number.isFinite(nowMs) && nowMs - updatedMs >= PROCESSING_STALE_MS;
  }
  return false;
}

function compareMediaTaskPriority(a, b) {
  return (Number(b.priority || 50) - Number(a.priority || 50)) || String(a.created_at || '').localeCompare(String(b.created_at || ''));
}

function mediaBlobBytes(blob) {
  const value = Number(blob?.size ?? blob?.byteLength ?? 0);
  return Number.isFinite(value) && value >= 0 ? value : 0;
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

function openMediaDb() {
  if (typeof indexedDB === 'undefined') {
    return Promise.reject(new Error('indexedDB unavailable'));
  }
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(TASK_STORE)) {
        const tasks = db.createObjectStore(TASK_STORE, { keyPath: 'artifact_id' });
        tasks.createIndex('status', 'status', { unique: false });
        tasks.createIndex('next_attempt_at', 'next_attempt_at', { unique: false });
      }
      if (!db.objectStoreNames.contains(BLOB_STORE)) {
        const blobs = db.createObjectStore(BLOB_STORE, { keyPath: 'artifact_id' });
        blobs.createIndex('byte_size', 'byte_size', { unique: false });
      } else {
        const blobs = request.transaction.objectStore(BLOB_STORE);
        if (!blobs.indexNames.contains('byte_size')) blobs.createIndex('byte_size', 'byte_size', { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('indexedDB open failed'));
  });
}

async function withStore(storeName, mode, fn) {
  return withStores([storeName], mode, (stores) => fn(stores[storeName]));
}

async function withStores(storeNames, mode, fn) {
  const db = await openMediaDb();
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

async function blobAccounting(blobs) {
  const totalCount = await requestToPromise(blobs.count());
  const indexedCount = await requestToPromise(blobs.index('byte_size').count());
  if (totalCount === indexedCount) {
    return new Promise((resolve, reject) => {
      let count = 0;
      let bytes = 0;
      const request = blobs.index('byte_size').openKeyCursor();
      request.onerror = () => reject(request.error || new Error('media blob accounting cursor failed'));
      request.onsuccess = () => {
        const cursor = request.result;
        if (!cursor) return resolve({ count, bytes });
        count += 1;
        bytes += Number(cursor.key || 0);
        cursor.continue();
      };
    });
  }
  return new Promise((resolve, reject) => {
    let count = 0;
    let bytes = 0;
    const request = blobs.openCursor();
    request.onerror = () => reject(request.error || new Error('legacy media blob accounting cursor failed'));
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return resolve({ count, bytes });
      const row = cursor.value;
      const byteSize = Number(row.byte_size ?? mediaBlobBytes(row.blob));
      count += 1;
      bytes += byteSize;
      if (row.byte_size === undefined) cursor.update({ ...row, byte_size: byteSize, metadata: { ...(row.metadata || {}), byte_size: byteSize } });
      cursor.continue();
    };
  });
}

async function putMediaTask(task) {
  const result = await putMediaTasks([task]);
  if (!result.accepted) throw new Error(result.reason);
  return result.written[0];
}

async function putMediaTasks(tasks = [], { maxItems = null } = {}) {
  const normalized = tasks.map(normalizeTask);
  if (normalized.some((task) => !task.artifact_id)) throw new Error('artifact_id required');
  return withStore(TASK_STORE, 'readwrite', async (store) => {
    const existing = await requestToPromise(store.getAll());
    const byId = new Map(existing.map((task) => [task.artifact_id, task]));
    const newIds = new Set(normalized.filter((task) => !byId.has(task.artifact_id)).map((task) => task.artifact_id));
    if (maxItems !== null && existing.length + newIds.size > Math.max(0, Number(maxItems) || 0)) {
      return { accepted: false, reason: 'media-task-quota', written: [], count: existing.length };
    }
    const written = [];
    for (const task of normalized) {
      const prior = byId.get(task.artifact_id);
      const merged = prior ? { ...prior, ...task, created_at: prior.created_at || task.created_at, updated_at: nowIso() } : task;
      await requestToPromise(store.put(merged));
      byId.set(merged.artifact_id, merged);
      written.push(merged);
    }
    return { accepted: true, written, count: byId.size };
  });
}

async function getAllTasks() {
  return withStore(TASK_STORE, 'readonly', (store) => requestToPromise(store.getAll()));
}

async function getDueMediaTasks(limit = 10, now = nowIso()) {
  const tasks = await getAllTasks();
  return tasks
    .filter((task) => mediaTaskIsDue(task, now))
    .sort(compareMediaTaskPriority)
    .slice(0, Math.max(1, Number(limit) || 10));
}

async function putFetchedBlob(artifactId, blob, metadata = {}, { maxTotalBytes = null, maxBlobBytes = null } = {}) {
  if (!artifactId) throw new Error('artifact_id required');
  const byteSize = mediaBlobBytes(blob);
  const row = { artifact_id: artifactId, blob, metadata: { ...metadata, byte_size: byteSize }, byte_size: byteSize, updated_at: nowIso() };
  return withStores([TASK_STORE, BLOB_STORE], 'readwrite', async ({ tasks, blobs }) => {
    const task = await requestToPromise(tasks.get(artifactId));
    if (!task) throw new Error('media task required before blob admission');
    const accounting = await blobAccounting(blobs);
    const prior = await requestToPromise(blobs.get(artifactId));
    const totalBytes = accounting.bytes;
    const projectedBytes = totalBytes - Number(prior?.byte_size ?? mediaBlobBytes(prior?.blob)) + byteSize;
    if (maxBlobBytes !== null && byteSize > Math.max(0, Number(maxBlobBytes) || 0)) {
      return { accepted: false, reason: 'media-blob-item-quota', byte_size: byteSize, total_bytes: totalBytes };
    }
    if (maxTotalBytes !== null && projectedBytes > Math.max(0, Number(maxTotalBytes) || 0)) {
      return { accepted: false, reason: 'media-blob-total-quota', byte_size: byteSize, total_bytes: totalBytes };
    }
    await requestToPromise(blobs.put(row));
    const updatedTask = { ...task, status: 'pending-upload', last_error: '', updated_at: nowIso() };
    await requestToPromise(tasks.put(updatedTask));
    return { accepted: true, row, task: updatedTask, total_bytes: projectedBytes };
  });
}

async function getFetchedBlob(artifactId) {
  if (!artifactId) return null;
  return withStore(BLOB_STORE, 'readonly', (store) => requestToPromise(store.get(artifactId)));
}

async function markMediaTask(artifactId, patch = {}, now = nowIso()) {
  if (!artifactId) throw new Error('artifact_id required');
  return withStore(TASK_STORE, 'readwrite', async (store) => {
    const existing = (await requestToPromise(store.get(artifactId))) || { artifact_id: artifactId, created_at: now };
    const updated = { ...existing, ...patch, updated_at: now };
    await requestToPromise(store.put(updated));
    return updated;
  });
}

async function deleteMediaTask(artifactId) {
  if (!artifactId) return;
  return withStores([TASK_STORE, BLOB_STORE], 'readwrite', async ({ tasks, blobs }) => {
    await requestToPromise(blobs.delete(artifactId));
    await requestToPromise(tasks.delete(artifactId));
  });
}

async function getMediaQueueStats() {
  return withStores([TASK_STORE, BLOB_STORE], 'readwrite', async ({ tasks, blobs }) => {
    const allTasks = await requestToPromise(tasks.getAll());
    const accounting = await blobAccounting(blobs);
    return {
      task_count: allTasks.length,
      blob_count: accounting.count,
      blob_bytes: accounting.bytes,
      by_status: allTasks.reduce((acc, task) => {
        acc[task.status] = (acc[task.status] || 0) + 1;
        return acc;
      }, {})
    };
  });
}

async function cleanupTerminalMediaTasks({ now = nowIso(), ttlMs = DEFAULT_TERMINAL_TTL_MS, limit = 50 } = {}) {
  const cutoff = Date.parse(now) - Math.max(0, Number(ttlMs) || 0);
  return withStores([TASK_STORE, BLOB_STORE], 'readwrite', async ({ tasks, blobs }) => {
    const allTasks = await requestToPromise(tasks.getAll());
    const expired = allTasks
      .filter((task) => TERMINAL_STATUSES.has(String(task.status)) && Date.parse(task.updated_at || task.created_at || '') <= cutoff)
      .sort((a, b) => String(a.updated_at || '').localeCompare(String(b.updated_at || '')))
      .slice(0, Math.max(0, Number(limit) || 0));
    for (const task of expired) {
      await requestToPromise(blobs.delete(task.artifact_id));
      await requestToPromise(tasks.delete(task.artifact_id));
    }
    return { deleted: expired.map((task) => task.artifact_id) };
  });
}

async function countMediaTasksByStatus() {
  const tasks = await getAllTasks();
  return tasks.reduce((acc, task) => {
    acc[task.status] = (acc[task.status] || 0) + 1;
    return acc;
  }, {});
}

class MemoryMediaQueueStore {
  constructor() {
    this.tasks = new Map();
    this.blobs = new Map();
    this.writeChain = Promise.resolve();
  }
  _exclusive(fn) {
    const run = this.writeChain.then(fn, fn);
    this.writeChain = run.then(() => undefined, () => undefined);
    return run;
  }
  async putMediaTask(task) {
    const result = await this.putMediaTasks([task]);
    if (!result.accepted) throw new Error(result.reason);
    return result.written[0];
  }
  async putMediaTasks(tasks = [], { maxItems = null } = {}) {
    return this._exclusive(async () => {
      const normalized = tasks.map(normalizeTask);
      if (normalized.some((task) => !task.artifact_id)) throw new Error('artifact_id required');
      const newIds = new Set(normalized.filter((task) => !this.tasks.has(task.artifact_id)).map((task) => task.artifact_id));
      if (maxItems !== null && this.tasks.size + newIds.size > Math.max(0, Number(maxItems) || 0)) {
        return { accepted: false, reason: 'media-task-quota', written: [], count: this.tasks.size };
      }
      const written = normalized.map((task) => {
        const prior = this.tasks.get(task.artifact_id);
        const merged = prior ? { ...prior, ...task, created_at: prior.created_at || task.created_at, updated_at: nowIso() } : task;
        this.tasks.set(merged.artifact_id, merged);
        return merged;
      });
      return { accepted: true, written, count: this.tasks.size };
    });
  }
  async getDueMediaTasks(limit = 10, now = nowIso()) {
    await this.writeChain;
    return Array.from(this.tasks.values())
      .filter((task) => mediaTaskIsDue(task, now))
      .sort(compareMediaTaskPriority)
      .slice(0, Math.max(1, Number(limit) || 10));
  }
  async putFetchedBlob(artifactId, blob, metadata = {}, { maxTotalBytes = null, maxBlobBytes = null } = {}) {
    return this._exclusive(async () => {
      if (!this.tasks.has(artifactId)) throw new Error('media task required before blob admission');
      const byteSize = mediaBlobBytes(blob);
      const totalBytes = Array.from(this.blobs.values()).reduce((total, item) => total + Number(item.byte_size ?? mediaBlobBytes(item.blob)), 0);
      const prior = this.blobs.get(artifactId);
      const projectedBytes = totalBytes - Number(prior?.byte_size ?? mediaBlobBytes(prior?.blob)) + byteSize;
      if (maxBlobBytes !== null && byteSize > Math.max(0, Number(maxBlobBytes) || 0)) return { accepted: false, reason: 'media-blob-item-quota', byte_size: byteSize, total_bytes: totalBytes };
      if (maxTotalBytes !== null && projectedBytes > Math.max(0, Number(maxTotalBytes) || 0)) return { accepted: false, reason: 'media-blob-total-quota', byte_size: byteSize, total_bytes: totalBytes };
      const row = { artifact_id: artifactId, blob, metadata: { ...metadata, byte_size: byteSize }, byte_size: byteSize, updated_at: nowIso() };
      this.blobs.set(artifactId, row);
      this.tasks.set(artifactId, { ...this.tasks.get(artifactId), status: 'pending-upload', last_error: '', updated_at: nowIso() });
      return { accepted: true, row, task: this.tasks.get(artifactId), total_bytes: projectedBytes };
    });
  }
  async getFetchedBlob(artifactId) {
    await this.writeChain;
    return this.blobs.get(artifactId) || null;
  }
  async markMediaTask(artifactId, patch = {}, now = nowIso()) {
    return this._exclusive(async () => {
      const existing = this.tasks.get(artifactId) || { artifact_id: artifactId, created_at: now };
      const updated = { ...existing, ...patch, updated_at: now };
      this.tasks.set(artifactId, updated);
      return updated;
    });
  }
  async deleteMediaTask(artifactId) {
    return this._exclusive(async () => {
      this.blobs.delete(artifactId);
      this.tasks.delete(artifactId);
    });
  }
  async getMediaQueueStats() {
    await this.writeChain;
    return {
      task_count: this.tasks.size,
      blob_count: this.blobs.size,
      blob_bytes: Array.from(this.blobs.values()).reduce((total, item) => total + Number(item.byte_size ?? mediaBlobBytes(item.blob)), 0),
      by_status: await this.countMediaTasksByStatus()
    };
  }
  async cleanupTerminalMediaTasks({ now = nowIso(), ttlMs = DEFAULT_TERMINAL_TTL_MS, limit = 50 } = {}) {
    return this._exclusive(async () => {
      const cutoff = Date.parse(now) - Math.max(0, Number(ttlMs) || 0);
      const expired = Array.from(this.tasks.values())
        .filter((task) => TERMINAL_STATUSES.has(String(task.status)) && Date.parse(task.updated_at || task.created_at || '') <= cutoff)
        .sort((a, b) => String(a.updated_at || '').localeCompare(String(b.updated_at || '')))
        .slice(0, Math.max(0, Number(limit) || 0));
      for (const task of expired) {
        this.blobs.delete(task.artifact_id);
        this.tasks.delete(task.artifact_id);
      }
      return { deleted: expired.map((task) => task.artifact_id) };
    });
  }
  async countMediaTasksByStatus() {
    await this.writeChain;
    return Array.from(this.tasks.values()).reduce((acc, task) => {
      acc[task.status] = (acc[task.status] || 0) + 1;
      return acc;
    }, {});
  }
}

const api = {
  openMediaDb,
  putMediaTask,
  putMediaTasks,
  getDueMediaTasks,
  putFetchedBlob,
  getFetchedBlob,
  markMediaTask,
  deleteMediaTask,
  getMediaQueueStats,
  cleanupTerminalMediaTasks,
  countMediaTasksByStatus,
  MemoryMediaQueueStore,
  mediaTaskIsDue,
  normalizeTask
};

globalThis.BrowserMemoryMediaQueue = api;
if (typeof module !== 'undefined') module.exports = api;
})();
