# Expand extension service-worker resilience coverage

## Status
open

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

Pending.

## New tickets / fog updates

Pending. If test harnessing Chrome extension APIs becomes large, split a separate harness ticket before adding many behavior tests.
