---
id: ADR-0061
status: accepted
date: 2026-07-14
decider: Michael
scope: repo
backfilled: false
supersedes: [ADR-0039]
superseded_by: []
related: [ADR-0036, ADR-0040, ADR-0046, REQ-035, REQ-036, REQ-045]
verification:
  - daemon/tests/integration/test_media_worker.py::test_media_worker_auto_drains_spool_after_guarded_media_root_recovers
  - daemon/tests/integration/test_media_storage.py::test_unavailable_external_media_root_spools_then_drains_with_hash_verification
  - daemon/tests/e2e/test_install_daily_driver.py::test_installer_stages_validates_swaps_and_restarts_services_in_order
---

# ADR-0061: Automatically drain the bounded media spool after guarded-root recovery

## Context

ADR-0039 separated final media from local SQLite and introduced an explicit, bounded local outage spool. Its drain was deliberately operator-executed while storage-tier safety matured. The production NAS is now a guarded SSHFS media root, but two gaps prevent unattended fault tolerance:

- the steady-state worker does not drain spooled media after the guarded root recovers;
- a hard systemd `Requires=` edge from BMD to the NAS mount prevents BMD from starting during a NAS outage, defeating local text/provenance availability.

The existing drain already streams bytes, verifies expected size and SHA-256, commits a compare-and-switch SQLite tier transition, tombstones the spool locator, and only then removes the local source. The missing behavior is bounded automatic orchestration, not a second transfer path.

## Decision

We will operate BMD as a guarded final media root plus bounded local durable spool:

1. `BMD_MEDIA_ROOT` remains the final disposable-media tier. Every read, write, and drain requires a mounted non-root ancestor and an exact `.bmd-media-root-id` match.
2. `BMD_MEDIA_SPOOL_ROOT` remains local, beneath the BMD data root, and must be paired with a positive hard byte cap. Production uses a 20 GiB cap.
3. When the guarded root is unavailable or has the wrong identity, new eligible media writes go only to the bounded spool. Local SQLite text/provenance capture continues.
4. At the start of each bounded media-worker pass, the worker checks guarded-root readiness. If ready, it drains at most the worker batch limit before claiming new fetch work. If unavailable, it defers without failing the worker loop.
5. Automatic drain uses the existing `drain_media_spool` state transition. It streams and verifies destination bytes, commits the `spool` to `media-root` authority switch, persists deletion intent, and removes the local source only after the switch commits.
6. A mid-copy, verification, transaction, or cleanup failure remains retryable. The authoritative local source is preserved until transfer authority commits; failed cleanup remains filesystem-accounted and visible to health/reconciliation.
7. The worker records redaction-safe drain status, selected/moved byte counts, errors, and cleanup failures. Daily-driver health reports current spool accounting, warns at 80% capacity, errors at the hard cap, and surfaces partial drain results.
8. BMD daemon and worker units must not hard-require an external media mount. A host-managed mount unit may be a soft `Wants=` plus `After=` dependency so startup tries the mount first but local capture and spool service remain available when it fails.
9. The manual `media-spool status` and dry-run-first `media-spool drain` commands remain available for inspection and bounded operator recovery.
10. Existing local final-tier media is migrated copy-first to the guarded NAS root. Source removal is a separate post-verification action after path counts, hashes, live reads, and health pass.

## Decision drivers

- preserve local searchable text and provenance through NAS outages;
- never create an unmounted shadow media directory;
- keep outage growth bounded under concurrent writers;
- recover automatically without weakening size/hash/identity checks;
- remove local copies only after durable remote authority is committed;
- keep automatic work bounded per worker pass and observable without logging content.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep explicit operator drain | Strong approval boundary | Requires manual recovery and leaves the spool occupied after ordinary outages | Rejected for steady-state recovery; CLI retained as override |
| Add a separate systemd drain timer | Process isolation | Duplicates scheduling, connection, audit, and concurrency boundaries | Rejected |
| Drain a bounded batch in the existing media worker | Reuses one state machine, interval, DB connection, and batch limit | Adds current-state storage recovery to each worker pass | Chosen |
| Make NAS mandatory with `Requires=` | Simple final-tier availability assumption | Prevents local capture during startup outages | Rejected |

## Consequences

- Positive: ordinary NAS disconnect/reconnect cycles recover without operator action.
- Positive: the transfer and deletion safety contract remains single-path and hash verified.
- Positive: BMD starts and preserves local text even when the NAS mount service is failed.
- Negative: an idle worker performs one guarded-root readiness check per interval.
- Negative: a prolonged outage eventually reaches the spool cap and rejects additional media while preserving existing bytes and text capture.
- Operational: a full or repeatedly partial spool drain is a health fault requiring mount, identity, capacity, or reconciliation diagnosis.

## Verification / validation

- Verification: guarded root absent at write time stores media in the local spool.
- Verification: wrong identity defers drain and preserves the local source.
- Verification: corrected identity causes the next worker pass to stream, verify, switch authority, and clean the source.
- Verification: existing failure-injection tests preserve local bytes on hash or compare-and-switch failure.
- Verification: installer-generated daemon and worker units contain no hard NAS `Requires=` dependency.
- Validation: live service startup with the NAS unit stopped keeps daemon and worker active and reports degraded guarded-root status with spool enabled.
- Validation: live remount causes the worker to drain a bounded canary from spool to NAS and return health to ready.

## Revisit triggers

- Split drain into its own service if transfer latency prevents worker fetch SLAs.
- Replace SSHFS-specific operations if a stable WSL NFS mount becomes available.
- Raise or lower the 20 GiB production cap only from measured ingest rate and local headroom.

## References

- [ADR-0039](0039-split-media-root-and-add-bounded-durable-spool.md)
- [ADR-0040](0040-use-durable-deletion-intents-and-reconciliation.md)
- [ADR-0046](0046-move-historical-media-correction-out-of-worker-loop.md)
