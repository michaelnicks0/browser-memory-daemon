# Expand extension service-worker resilience coverage

## Status
closed

## Question
Can extension tests cover service-worker resilience when the daemon is down, the token/config is stale, capture is paused/resumed, queues persist across worker lifetimes, and media uploads retry without data loss?

## Type
task

## Inputs / links

- `extension/src/service_worker.js`
- `extension/src/content_script.js`
- `extension/src/media_queue.js`
- `extension/src/queue.js`
- `extension/tests/unit/*.test.js`
- `docs/USER_GUIDE.md#chrome-extension-controls`

## Blocks / blocked by

- Blocks: stronger daily-driver claims about Chrome-side reliability.
- Blocked by: none; ticket 001 preferred.

## Resolution

Closed in this slice. Added a Node `vm` service-worker harness around the real `extension/src/service_worker.js` with mocked Chrome extension APIs, storage, fetch, and the media IndexedDB queue implementation. Coverage now proves:

- daemon-down capture attempts remain in `captureQueue` and drain after a simulated service-worker reload;
- missing-token and paused states skip new capture queue mutation, then resume cleanly;
- injection honors stale-token, paused, already-injected, and strict URL-block controls;
- browser-side media upload retries preserve fetched blobs until a later successful upload deletes the task/blob.

Evidence:

```bash
cd extension && npm test
# 27 node:test tests passed

BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh
# pytest passed; extension node:test 27/27; extension build; real Chrome for Testing e2e ok; secret scan passed
```

## New tickets / fog updates

No new tickets. The harness stayed small and local to `extension/tests/unit/service_worker.test.js`; no separate harness ticket is needed.
