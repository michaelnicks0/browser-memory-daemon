(function () {
const DB_NAME = 'browser-memory-media-v1';
const DB_VERSION = 1;
const TASK_STORE = 'tasks';
const BLOB_STORE = 'blobs';
const DEFAULT_MAX_ATTEMPTS = 5;
const PROCESSING_STALE_MS = 2 * 60 * 1000;
const DUE_STATUSES = new Set(['pending-fetch', 'pending-upload', 'retrying']);
const PROCESSING_STATUSES = new Set(['fetching', 'uploading']);

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
        db.createObjectStore(BLOB_STORE, { keyPath: 'artifact_id' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('indexedDB open failed'));
  });
}

async function withStore(storeName, mode, fn) {
  const db = await openMediaDb();
  try {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    const value = await fn(store);
    await txComplete(tx);
    return value;
  } finally {
    db.close();
  }
}

async function putMediaTask(task) {
  const normalized = normalizeTask(task);
  if (!normalized.artifact_id) throw new Error('artifact_id required');
  return withStore(TASK_STORE, 'readwrite', async (store) => {
    const existing = await requestToPromise(store.get(normalized.artifact_id));
    const merged = existing ? { ...existing, ...normalized, created_at: existing.created_at || normalized.created_at, updated_at: nowIso() } : normalized;
    await requestToPromise(store.put(merged));
    return merged;
  });
}

async function putMediaTasks(tasks = []) {
  const written = [];
  for (const task of tasks) written.push(await putMediaTask(task));
  return written;
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

async function putFetchedBlob(artifactId, blob, metadata = {}) {
  if (!artifactId) throw new Error('artifact_id required');
  const row = { artifact_id: artifactId, blob, metadata, updated_at: nowIso() };
  return withStore(BLOB_STORE, 'readwrite', async (store) => {
    await requestToPromise(store.put(row));
    return row;
  });
}

async function getFetchedBlob(artifactId) {
  if (!artifactId) return null;
  return withStore(BLOB_STORE, 'readonly', (store) => requestToPromise(store.get(artifactId)));
}

async function deleteFetchedBlob(artifactId) {
  if (!artifactId) return;
  return withStore(BLOB_STORE, 'readwrite', (store) => requestToPromise(store.delete(artifactId)));
}

async function markMediaTask(artifactId, patch = {}) {
  if (!artifactId) throw new Error('artifact_id required');
  return withStore(TASK_STORE, 'readwrite', async (store) => {
    const existing = (await requestToPromise(store.get(artifactId))) || { artifact_id: artifactId, created_at: nowIso() };
    const updated = { ...existing, ...patch, updated_at: nowIso() };
    await requestToPromise(store.put(updated));
    return updated;
  });
}

async function deleteMediaTask(artifactId) {
  if (!artifactId) return;
  await deleteFetchedBlob(artifactId);
  return withStore(TASK_STORE, 'readwrite', (store) => requestToPromise(store.delete(artifactId)));
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
  }
  async putMediaTask(task) {
    const normalized = normalizeTask(task);
    const existing = this.tasks.get(normalized.artifact_id);
    const merged = existing ? { ...existing, ...normalized, created_at: existing.created_at || normalized.created_at, updated_at: nowIso() } : normalized;
    this.tasks.set(merged.artifact_id, merged);
    return merged;
  }
  async getDueMediaTasks(limit = 10, now = nowIso()) {
    return Array.from(this.tasks.values())
      .filter((task) => mediaTaskIsDue(task, now))
      .sort(compareMediaTaskPriority)
      .slice(0, Math.max(1, Number(limit) || 10));
  }
  async putFetchedBlob(artifactId, blob, metadata = {}) {
    this.blobs.set(artifactId, { artifact_id: artifactId, blob, metadata, updated_at: nowIso() });
    return this.blobs.get(artifactId);
  }
  async getFetchedBlob(artifactId) {
    return this.blobs.get(artifactId) || null;
  }
  async markMediaTask(artifactId, patch = {}) {
    const existing = this.tasks.get(artifactId) || { artifact_id: artifactId, created_at: nowIso() };
    const updated = { ...existing, ...patch, updated_at: nowIso() };
    this.tasks.set(artifactId, updated);
    return updated;
  }
  async deleteMediaTask(artifactId) {
    this.blobs.delete(artifactId);
    this.tasks.delete(artifactId);
  }
  async countMediaTasksByStatus() {
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
  countMediaTasksByStatus,
  MemoryMediaQueueStore,
  mediaTaskIsDue,
  normalizeTask
};

globalThis.BrowserMemoryMediaQueue = api;
if (typeof module !== 'undefined') module.exports = api;
})();
