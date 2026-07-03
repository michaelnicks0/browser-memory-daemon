# Optimize read-model query and index performance

## Status
blocked

## Question
Given benchmark output and query plans, which read-model paths need indexes, pagination, bounded detail payloads, query rewrites, or reduced synchronous audit writes to remain fast as the SQLite DB grows?

## Type
task

## Inputs / links

- Ticket 009 benchmark harness output
- `daemon/src/browser_memory_daemon/ops.py`
- `daemon/src/browser_memory_daemon/search.py`
- `daemon/src/browser_memory_daemon/schema.sql`
- `docs/api.md`

## Scope notes from late ticket-004 audit

- Search, recent, timeline, detail, doctor, and queue/status reads synchronously insert audit rows today. Benchmark and decide whether read-audit writes should be sampled, disabled for high-frequency reads, or moved to an async/batched writer.

## Blocks / blocked by

- Blocks: long-term daily-driver performance and UI responsiveness.
- Blocked by: ticket 009.

## Resolution

Pending.

## New tickets / fog updates

Pending. If API pagination contracts change, update `docs/api.md` and consider an ADR if interface semantics materially change.
