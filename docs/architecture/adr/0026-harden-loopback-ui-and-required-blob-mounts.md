---
id: ADR-0026
status: accepted
date: 2026-07-10
decision_date: 2026-07-10
decider: Operator
scope: repo
supersedes: []
superseded_by: []
related:
  - docs/architecture/adr/0012-bootstrap-local-ui-token-from-daemon.md
  - docs/architecture/adr/0021-use-configurable-nas-blob-root-with-local-sqlite.md
  - docs/security-model.md
  - docs/daily-driver-deployment.md
  - docs/USER_GUIDE.md
---

# ADR-0026: Harden loopback UI and required blob mounts

## Context

The daily-driver dashboard intentionally receives the daemon bearer token through the same-origin `/ui` HTML bootstrap. That keeps the local dashboard usable without manual token paste, but it makes the `/ui` shell more sensitive than ordinary static assets.

The blob root is configurable so clean-text and media blobs can live on a WSL-visible NAS/NFS/SSHFS filesystem while SQLite/WAL stays local. If a mount disappears and the path is recreated as an ordinary local directory, the daemon could silently write new blobs to the wrong storage tier.

## Decision

We will harden Phase 0.5 with two explicit guards:

1. `/ui` remains unauthenticated local HTML, but the daemon rejects UI-shell/static-asset requests whose `Host` header is not loopback (`127.0.0.0/8`, `::1`, `localhost`, or `*.localhost`). Memory/admin APIs still require the bearer token.
2. Add optional `BMD_REQUIRE_BLOB_ROOT_MOUNT=1`. When enabled, runtime config, the daily-driver installer, and daily-driver health treat `BMD_BLOB_ROOT` as valid only if it has a non-root mounted ancestor. This prevents silent fallback writes into an empty local mountpoint.

The default remains compatible: `BMD_REQUIRE_BLOB_ROOT_MOUNT=0`, so local WSL blob roots continue to work without mount inspection.

## Consequences

- Positive: token-bootstrap UI is still convenient but less likely to answer accidental non-loopback Host-header access.
- Positive: NAS-backed blob deployments can fail fast when the storage mount is absent.
- Positive: installer dry-run validates the mount requirement before creating config/data/state/blob directories.
- Positive: daily-driver health reports the mount guard in redaction-safe aggregate status.
- Neutral: local WSL-only installs keep the existing default behavior by leaving `BMD_REQUIRE_BLOB_ROOT_MOUNT` unset or `0`.
- Negative: operators using a NAS blob root must ensure the mount exists before service startup when the guard is enabled.

## Verification / validation

- Verification: `daemon/tests/e2e/test_ui_dashboard_smoke.py` covers UI token bootstrap, token-free static assets, path traversal rejection, and non-loopback Host-header rejection.
- Verification: `daemon/tests/unit/test_config.py` covers required blob-root mount positive and negative config paths.
- Verification: `daemon/tests/e2e/test_daily_driver_install.py` covers non-mutating installer dry-runs and fail-before-write behavior when the required mount is absent.
- Verification: `daemon/tests/unit/test_daily_driver_health.py` covers required blob-root mount health errors.

## Revisit triggers

- Supersede this ADR if `/ui` stops carrying a bearer token in HTML.
- Supersede this ADR before intentionally exposing the UI through a remote tunnel or non-loopback interface.
- Supersede this ADR if blob storage gains a stronger mount identity check, such as expected device IDs, filesystem UUIDs, or signed mount metadata.

## References

- `daemon/src/browser_memory_daemon/app.py`
- `daemon/src/browser_memory_daemon/config.py`
- `daemon/src/browser_memory_daemon/daily_driver_health.py`
- `scripts/install-daily-driver.sh`
