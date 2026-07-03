# Optimize read-model query and index performance

## Status
blocked

## Question
Given benchmark output and query plans, which read-model paths need indexes, pagination, bounded detail payloads, or query rewrites to remain fast as the SQLite DB grows?

## Type
task

## Inputs / links

- Ticket 009 benchmark harness output
- `daemon/src/browser_memory_daemon/ops.py`
- `daemon/src/browser_memory_daemon/search.py`
- `daemon/src/browser_memory_daemon/schema.sql`
- `docs/api.md`

## Blocks / blocked by

- Blocks: long-term daily-driver performance and UI responsiveness.
- Blocked by: ticket 009.

## Resolution

Pending.

## New tickets / fog updates

Pending. If API pagination contracts change, update `docs/api.md` and consider an ADR if interface semantics materially change.
