# Design retention, compaction, and backup posture

## Status
open

## Question
What retention, compaction, export, and backup posture should Browser Memory Daemon adopt for long-term high-volume use while preserving local-first recall and deletion semantics?

## Type
research

## Inputs / links

- `docs/STATUS.md#pending-roadmap-lanes`
- `docs/ARCHITECTURE.md#storage-model`
- `docs/api.md#media-artifact-apis`
- `daemon/src/browser_memory_daemon/schema.sql`
- `daemon/src/browser_memory_daemon/forget.py`
- Baseline DB/media growth evidence from ticket 001

## Blocks / blocked by

- Blocks: retention implementation tickets and any backup/export feature.
- Blocked by: none. Ticket 001 provides current DB/media/headroom evidence; likely ADR-worthy.

## Resolution

Pending.

## New tickets / fog updates

Pending. This is likely ADR-worthy because it affects storage, deletion, backup, and operator data-retention semantics.
