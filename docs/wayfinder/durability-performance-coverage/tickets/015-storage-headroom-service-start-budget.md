# Add storage-headroom and service-start failure budget checks

## Status
closed

## Question
Can Browser Memory Daemon detect low filesystem/runtime headroom and service-start failure churn before the daily-driver media worker reaches systemd `No space left on device` / `resources` failures?

## Type
task

## Inputs / links

- Ticket 001 baseline: 7-day media-worker journal history contained 919 warning-or-higher lines, dominated by 900 resolved systemd start-failure lines from 2026-06-27 to 2026-06-28.
- `scripts/install-daily-driver.sh`
- `docs/TESTS.md#daily-driver-smoke-checklist`
- `docs/USER_GUIDE.md`
- `daemon/src/browser_memory_daemon/ops.py`
- `daemon/src/browser_memory_daemon/cli.py`
- Current runtime locations: WSL data/state/config roots and Windows extension artifact root.

## Blocks / blocked by

- Blocks: hard operational alerting budgets, installer safety, and long-running soak gates.
- Blocked by: none. Coordinate with ticket 002 if the health snapshot command is implemented first.

## Resolution

Implemented daily-driver health/preflight budget checks:

- storage paths now report `headroom.status` with warning/error thresholds for free bytes and used percent;
- systemd unit status now reports `restart_budget` from `NRestarts`;
- recent journal inspection now reports `service_start_budget` for start-limit/resource/no-space failure patterns;
- summary scoring turns hard headroom/restart/start-failure thresholds into health errors while preserving redaction-safe output;
- operator docs describe default thresholds and local `BMD_HEALTH_*` overrides;
- ADR-0018 records the hard local-health semantics.

Evidence:

```bash
/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/unit/test_daily_driver_health.py daemon/tests/e2e/test_cli_admin.py
# 5 passed

./scripts/daily-driver-health.sh --journal-since '1 hour ago' --no-fail >/tmp/bmd_daily_health_015.json
# ok=True status=warning storage_paths=6 daemon_start_budget=ok media_start_budget=ok

BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python ./scripts/run-e2e.sh
# pytest passed; extension node:test 27/27; extension build; real Chrome for Testing all+strict matrix ok; secret scan passed

/tmp/browser-memory-daemon-verify-venv/bin/python scripts/generate_test_inventory.py --check
# 106 tests / 21 files

/tmp/browser-memory-daemon-verify-venv/bin/python scripts/render_docs.py --repo . --slug browser-memory-daemon --check
# 74 rendered docs match source
```

## New tickets / fog updates

Hard local-health thresholds are documented in ADR-0018. Ticket 012 should use the explicit headroom output when designing retention/compaction/checkpoint/backup policy, but no new implementation ticket is required here.
