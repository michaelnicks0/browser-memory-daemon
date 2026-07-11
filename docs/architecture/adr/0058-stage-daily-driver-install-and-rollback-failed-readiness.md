---
id: ADR-0058
status: accepted
date: 2026-07-10
decision_date: 2026-07-10
decider: Operator
scope: repo
supersedes: []
superseded_by: []
related:
  - ADR-0012
  - ADR-0021
  - ADR-0041
implementation_status: implemented
implementation:
  - daemon/src/browser_memory_daemon/config.py
  - scripts/install-daily-driver.sh
  - daemon/tests/unit/test_config.py
  - daemon/tests/e2e/test_install_daily_driver.py
  - docs/daily-driver-deployment.md
verification:
  - bash -n scripts/install-daily-driver.sh
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/e2e/test_install_daily_driver.py
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-fast-gate.sh
---

# ADR-0058: Stage Daily-Driver Installation and Roll Back Failed Readiness

## Context

The daily-driver installer built the extension and then deleted the installed extension directory in place. It wrote the token, environment file, and systemd units directly before validating the complete extension artifact, restarted both services together, and had no automatic recovery if readiness failed. A build, patch, service, or health failure could therefore leave a mixed generation or remove the previous unpacked extension bytes.

Repository delivery must prove failure recovery without applying the installer to the live daily driver. The extension destination is on the Windows filesystem while configuration and units are WSL-local, so one cross-filesystem atomic transaction is impossible. The practical safety boundary is staged validation plus explicit rollback for caught failures.

## Decision

1. Install and dry-run validate that the extension destination is absolute, is neither a filesystem root nor its direct child, and traverses no symlink before any destination write or recursive removal. The configurable destination name remains compatible.
2. Default daemon config/data/state roots honor `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and `XDG_STATE_HOME`, matching the installer's staged destinations. An explicit `BMD_RUNTIME_ROOT` remains authoritative when set.
3. Token, environment, and unit files are prepared under a private WSL state-directory stage. Existing versions and absence markers are copied into a private rollback directory before publication.
4. `extension/dist` is built first and copied to a uniquely named sibling of the installed extension. The staged copy is patched at the actual configuration owners (`config_store.js`, `options.js`, and `popup.js`) and validated for required non-empty files, valid Manifest V3 JSON, and destination disk headroom.
5. An existing database receives a read-only `migrate --check` preflight. Pending or incompatible schema work blocks installation; the installer never applies migrations implicitly. Fresh installs without a database skip this check.
6. Publication uses same-directory temporary files plus rename for WSL files. The extension is replaced by renaming the current directory to a unique sibling backup and renaming the validated stage into place.
7. The daemon unit is enabled, restarted, checked active, and checked over loopback before the media worker is enabled, restarted, and checked active. Windows loopback health remains the final readiness check when PowerShell is available.
8. Any caught failure after publication restores the prior token, environment, units, extension directory, enablement, and active/inactive service state. Restored services are checked active when they were active before installation.
9. A successful rollback preserves the original installer failure status and reports completion. If artifacts restore but prior service readiness cannot be recovered, the installer exits `70` and prints `ROLLBACK INCOMPLETE`; it never reports ordinary success.
10. Successful installation writes a private redaction-safe evidence manifest under the state directory with extension counts/bytes, the extension-manifest hash, and published file names/modes/hashes. It contains no token value.
11. Successful cleanup removes only uniquely named installer-owned stage and backup paths. Stale paths from `SIGKILL`, power loss, or host failure are not glob-deleted automatically.

## Consequences

### Positive

- Build and validation failures cannot remove the installed extension.
- Injected post-publication readiness failure restores byte-identical prior extension/config/unit/token fixtures.
- Service sequencing prevents the worker from restarting against an unready daemon.
- Pending schema work and unsafe extension destinations fail before publication.
- Rollback failure is explicit and distinguishable from the original readiness failure.

### Negative

- WSL config files and the Windows extension directory cannot participate in one crash-atomic transaction.
- `SIGKILL`, power loss, or WSL/Windows filesystem failure can leave a sibling stage/backup or a mixed publication requiring operator inspection.
- A successful install removes the transient prior extension backup after readiness; long-term version rollback remains a source-control/install operation.
- The installer performs an extension build and may take longer than the former destructive copy path.

### Neutral

- Chrome still requires the operator to reload the unpacked extension after a successful install.
- The installer does not apply database migrations and does not modify NAS contents beyond existing guarded runtime behavior.
- Synthetic tests use isolated XDG/Windows-like roots, a fake `systemctl`, and a loopback fixture server; they do not touch live services or Chrome profiles.

## Verification

- Success-path tests prove staged extension validation, token/policy patching, evidence-manifest creation, cleanup, and daemon-before-worker restart ordering.
- Injected worker-readiness failure proves byte-identical restoration of prior token, env, units, and extension plus prior service-state restart.
- Injected rollback-service failure proves exit `70` and visible `ROLLBACK INCOMPLETE` reporting while file artifacts are still restored.
- Dry-run tests reject an unsafe extension destination before creating config, data, state, or extension paths.
- Shell syntax, focused pytest, the hermetic fast gate, broad repository gate, and generated-document checks are required before commit.

## Rollback

Revert the installer, tests, ADR, requirement evidence, deployment docs, and generated artifacts together. This repository-only change performs no live installation. Runtime install-history manifests created by future approved installs are local evidence and are not deleted by a source rollback.
