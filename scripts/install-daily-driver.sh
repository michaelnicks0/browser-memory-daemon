#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -n "${BMD_PYTHON:-}" ]; then
  PY="$BMD_PYTHON"
elif command -v python3.11 >/dev/null 2>&1; then
  PY="$(command -v python3.11)"
else
  PY="$(command -v python3)"
fi
WIN_USER="${BMD_WINDOWS_USER:-${USER:-${LOGNAME:-}}}"
if [ -z "$WIN_USER" ]; then
  echo "Set BMD_WINDOWS_USER or BMD_WINDOWS_EXTENSION_DIR so the installer can locate the Windows profile." >&2
  exit 1
fi
EXT_DIR="${BMD_WINDOWS_EXTENSION_DIR:-/mnt/c/Users/${WIN_USER}/AppData/Local/browser-memory-daemon/extension}"
CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/browser-memory-daemon"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/browser-memory-daemon"
BLOB_DIR="${BMD_BLOB_ROOT:-$DATA_DIR/blobs}"
DERIVATIVE_DIR="${BMD_DERIVATIVE_ROOT:-$BLOB_DIR}"
MEDIA_DIR="${BMD_MEDIA_ROOT:-$BLOB_DIR/media}"
MEDIA_SPOOL_DIR="${BMD_MEDIA_SPOOL_ROOT:-}"
MAX_MEDIA_SPOOL_BYTES="${BMD_MAX_MEDIA_SPOOL_BYTES:-0}"
MAX_MEDIA_INFLIGHT_BYTES="${BMD_MAX_MEDIA_INFLIGHT_BYTES:-524288000}"
MAX_MEDIA_CONCURRENT_REQUESTS="${BMD_MAX_MEDIA_CONCURRENT_REQUESTS:-4}"
MEDIA_ROOT_IDENTITY="${BMD_MEDIA_ROOT_IDENTITY:-}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/browser-memory-daemon"
UNIT_DIR="$HOME/.config/systemd/user"
TOKEN_FILE="$CFG_DIR/token"
ENV_FILE="$CFG_DIR/env"
UNIT_FILE="$UNIT_DIR/browser-memory-daemon.service"
WORKER_UNIT_FILE="$UNIT_DIR/browser-memory-media-worker.service"
HOST="${BMD_HOST:-127.0.0.1}"
PORT="${BMD_PORT:-8765}"
POLICY_MODE="${BMD_POLICY_MODE:-all}"
REQUIRE_BLOB_ROOT_MOUNT="${BMD_REQUIRE_BLOB_ROOT_MOUNT:-0}"
REQUIRE_MEDIA_ROOT_MOUNT="${BMD_REQUIRE_MEDIA_ROOT_MOUNT:-$REQUIRE_BLOB_ROOT_MOUNT}"
PS="${BMD_POWERSHELL:-/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe}"
MODE=install

usage() {
  cat <<'EOF'
Usage: scripts/install-daily-driver.sh [--dry-run|--check]

Install/refresh stages protected WSL config, systemd user units, and the
Windows-local unpacked extension artifact, then publishes and verifies each
service in order. A caught readiness failure restores the prior generation.

Modes:
  --dry-run  Validate inputs and print the planned writes; make no changes.
  --check    Run the redaction-safe daily-driver health/artifact check only;
             do not build, copy, write units, rotate tokens, or restart services.
EOF
}

check_blob_root_mount_guard() {
  "$PY" - "$MEDIA_DIR" "$REQUIRE_MEDIA_ROOT_MOUNT" "$MEDIA_ROOT_IDENTITY" <<'PY'
from pathlib import Path
import sys

media_root = Path(sys.argv[1]).expanduser().resolve(strict=False)
enabled = str(sys.argv[2]).strip().lower() in {"1", "true", "yes", "on"}
identity = str(sys.argv[3]).strip()
if not enabled:
    raise SystemExit(0)
if not identity:
    raise SystemExit("BMD_MEDIA_ROOT_IDENTITY is required when the media-root mount guard is enabled")
mounted = False
for candidate in (media_root, *media_root.parents):
    if candidate.parent == candidate:
        continue
    try:
        if candidate.exists() and candidate.is_mount():
            mounted = True
            break
    except OSError:
        pass
if not mounted:
    raise SystemExit(f"media root has no non-root mounted ancestor: {media_root}")
marker = media_root / ".bmd-media-root-id"
if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != identity:
    raise SystemExit(f"media root identity marker missing or mismatched: {marker}")
PY
}

check_extension_destination_guard() {
  "$PY" - "$EXT_DIR" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1]).expanduser()
if not path.is_absolute():
    raise SystemExit(f"extension destination must be absolute: {path}")
resolved = path.resolve(strict=False)
if resolved == Path(resolved.anchor) or resolved.parent == Path(resolved.anchor):
    raise SystemExit(f"extension destination cannot be a filesystem root or direct child: {resolved}")
if path.is_symlink() or path.absolute() != resolved:
    raise SystemExit(f"extension destination and its ancestors must not be symlinks: {path}")
PY
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) MODE=dry-run ;;
    --check) MODE=check ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ ! -x "$PY" ]; then
  echo "Python runtime not executable: $PY" >&2
  exit 1
fi

PY_VERSION="$($PY - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"Python 3.11+ is required, got {sys.version.split()[0]}")
print(sys.version.split()[0])
PY
)" || {
  "$PY" --version >&2 || true
  exit 1
}

if [ "$MODE" = "check" ] && [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  HOST="${BMD_HOST:-$HOST}"
  PORT="${BMD_PORT:-$PORT}"
  POLICY_MODE="${BMD_POLICY_MODE:-$POLICY_MODE}"
  BLOB_DIR="${BMD_BLOB_ROOT:-$BLOB_DIR}"
  DERIVATIVE_DIR="${BMD_DERIVATIVE_ROOT:-$DERIVATIVE_DIR}"
  MEDIA_DIR="${BMD_MEDIA_ROOT:-$MEDIA_DIR}"
  MEDIA_SPOOL_DIR="${BMD_MEDIA_SPOOL_ROOT:-$MEDIA_SPOOL_DIR}"
  MAX_MEDIA_SPOOL_BYTES="${BMD_MAX_MEDIA_SPOOL_BYTES:-$MAX_MEDIA_SPOOL_BYTES}"
  MAX_MEDIA_INFLIGHT_BYTES="${BMD_MAX_MEDIA_INFLIGHT_BYTES:-$MAX_MEDIA_INFLIGHT_BYTES}"
  MAX_MEDIA_CONCURRENT_REQUESTS="${BMD_MAX_MEDIA_CONCURRENT_REQUESTS:-$MAX_MEDIA_CONCURRENT_REQUESTS}"
  MEDIA_ROOT_IDENTITY="${BMD_MEDIA_ROOT_IDENTITY:-$MEDIA_ROOT_IDENTITY}"
  REQUIRE_BLOB_ROOT_MOUNT="${BMD_REQUIRE_BLOB_ROOT_MOUNT:-$REQUIRE_BLOB_ROOT_MOUNT}"
  REQUIRE_MEDIA_ROOT_MOUNT="${BMD_REQUIRE_MEDIA_ROOT_MOUNT:-$REQUIRE_BLOB_ROOT_MOUNT}"
fi

case "$POLICY_MODE" in
  all|recall|balanced|strict) ;;
  *) echo "BMD_POLICY_MODE must be one of: all, recall, balanced, strict" >&2; exit 1 ;;
esac
case "${REQUIRE_MEDIA_ROOT_MOUNT,,}" in
  0|1|true|false|yes|no|on|off) ;;
  *) echo "BMD_REQUIRE_MEDIA_ROOT_MOUNT must be boolean-like: 0/1/true/false/yes/no/on/off" >&2; exit 1 ;;
esac

check_blob_root_mount_guard
if [ "$MODE" != "check" ]; then
  check_extension_destination_guard
fi

if [ "$MODE" = "dry-run" ]; then
  cat <<EOF
Daily-driver install dry run; no files, services, or Chrome artifacts will be changed.

Resolved inputs:
  Python: $PY ($PY_VERSION)
  Policy mode: $POLICY_MODE
  Require media mount: $REQUIRE_MEDIA_ROOT_MOUNT
  Host/port: $HOST:$PORT
  Config dir: $CFG_DIR
  Data dir: $DATA_DIR
  Blob dir: $BLOB_DIR
  Derivative dir: $DERIVATIVE_DIR
  Media dir: $MEDIA_DIR
  Media spool dir: ${MEDIA_SPOOL_DIR:-disabled}
  Media spool cap: $MAX_MEDIA_SPOOL_BYTES
  Media in-flight byte cap: $MAX_MEDIA_INFLIGHT_BYTES
  Media concurrent request cap: $MAX_MEDIA_CONCURRENT_REQUESTS
  State dir: $STATE_DIR
  Token file: $TOKEN_FILE
  Environment file: $ENV_FILE
  Daemon unit: $UNIT_FILE
  Media-worker unit: $WORKER_UNIT_FILE
  Windows extension artifact dir: $EXT_DIR

Install/refresh would:
  - create protected WSL config/data/state/derivative directories without creating an external media shadow root;
  - verify the configured media root mount and identity marker when BMD_REQUIRE_MEDIA_ROOT_MOUNT=1;
  - create or reuse the token file, or rotate it if BMD_ROTATE_TOKEN=1;
  - write the protected EnvironmentFile with token/policy plus derivative, guarded-media, and bounded-spool settings;
  - write systemd user units that read the EnvironmentFile instead of passing tokens in ExecStart;
  - build and validate an adjacent extension stage, then atomically swap it into the Windows-local artifact dir;
  - stage protected token/environment/unit files and preserve rollback copies before publication;
  - daemon-reload, restart and verify the daemon, then restart and verify the media worker;
  - restore prior files, extension artifact, enablement, and service state if readiness fails.

Chrome still requires the manual reload step after a real install:
  chrome://extensions → Browser Memory Daemon → Reload
EOF
  exit 0
fi

if [ "$MODE" = "check" ]; then
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
    HOST="${BMD_HOST:-$HOST}"
    PORT="${BMD_PORT:-$PORT}"
    POLICY_MODE="${BMD_POLICY_MODE:-$POLICY_MODE}"
    BLOB_DIR="${BMD_BLOB_ROOT:-$BLOB_DIR}"
    DERIVATIVE_DIR="${BMD_DERIVATIVE_ROOT:-$DERIVATIVE_DIR}"
    MEDIA_DIR="${BMD_MEDIA_ROOT:-$MEDIA_DIR}"
    MEDIA_SPOOL_DIR="${BMD_MEDIA_SPOOL_ROOT:-$MEDIA_SPOOL_DIR}"
    MAX_MEDIA_SPOOL_BYTES="${BMD_MAX_MEDIA_SPOOL_BYTES:-$MAX_MEDIA_SPOOL_BYTES}"
    MAX_MEDIA_INFLIGHT_BYTES="${BMD_MAX_MEDIA_INFLIGHT_BYTES:-$MAX_MEDIA_INFLIGHT_BYTES}"
    MAX_MEDIA_CONCURRENT_REQUESTS="${BMD_MAX_MEDIA_CONCURRENT_REQUESTS:-$MAX_MEDIA_CONCURRENT_REQUESTS}"
    MEDIA_ROOT_IDENTITY="${BMD_MEDIA_ROOT_IDENTITY:-$MEDIA_ROOT_IDENTITY}"
    REQUIRE_BLOB_ROOT_MOUNT="${BMD_REQUIRE_BLOB_ROOT_MOUNT:-$REQUIRE_BLOB_ROOT_MOUNT}"
    REQUIRE_MEDIA_ROOT_MOUNT="${BMD_REQUIRE_MEDIA_ROOT_MOUNT:-$REQUIRE_BLOB_ROOT_MOUNT}"
  fi
  if [ ! -s "$TOKEN_FILE" ]; then
    echo "Browser Memory Daemon token file missing or empty: $TOKEN_FILE" >&2
    exit 1
  fi
  TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
  cd "$ROOT"
  BMD_API_TOKEN="$TOKEN" PYTHONPATH="$ROOT/daemon/src${PYTHONPATH:+:$PYTHONPATH}" \
    exec "$PY" -m browser_memory_daemon --host "$HOST" --port "$PORT" --policy-mode "$POLICY_MODE" \
      daily-driver-health --extension-dir "$EXT_DIR"
fi

mkdir -p "$CFG_DIR" "$DATA_DIR" "$DERIVATIVE_DIR" "$STATE_DIR" "$UNIT_DIR" "$(dirname "$EXT_DIR")"
chmod 700 "$CFG_DIR" "$STATE_DIR"

STAGE_ROOT="$(mktemp -d "$STATE_DIR/install-stage.XXXXXX")"
EXT_STAGE="$(mktemp -d "${EXT_DIR}.stage.XXXXXX")"
EXT_BACKUP="${EXT_DIR}.backup.$$"
PUBLISH_STARTED=0
EXT_PUBLISHED=0
PRIOR_DAEMON_ACTIVE=0
PRIOR_WORKER_ACTIVE=0
PRIOR_DAEMON_ENABLED=0
PRIOR_WORKER_ENABLED=0

cleanup_install_stage() {
  if [ -n "${EXT_STAGE:-}" ] && [ -e "$EXT_STAGE" ]; then
    rm -rf -- "$EXT_STAGE"
  fi
  if [ -n "${STAGE_ROOT:-}" ] && [ -e "$STAGE_ROOT" ]; then
    rm -rf -- "$STAGE_ROOT"
  fi
}

restore_file() {
  local target="$1"
  local name="$2"
  if [ -e "$STAGE_ROOT/backups/$name.absent" ]; then
    rm -f -- "$target"
  elif [ -e "$STAGE_ROOT/backups/$name" ]; then
    cp -a -- "$STAGE_ROOT/backups/$name" "$target"
  fi
}

rollback_install() {
  local rc=$?
  trap - ERR
  set +e
  if [ "$PUBLISH_STARTED" = "1" ]; then
    local rollback_failed=0
    echo "Install readiness failed; restoring prior daily-driver artifacts." >&2
    restore_file "$TOKEN_FILE" token || rollback_failed=1
    restore_file "$ENV_FILE" env || rollback_failed=1
    restore_file "$UNIT_FILE" daemon-unit || rollback_failed=1
    restore_file "$WORKER_UNIT_FILE" worker-unit || rollback_failed=1
    if [ "$EXT_PUBLISHED" = "1" ]; then
      rm -rf -- "$EXT_DIR" || rollback_failed=1
    fi
    if [ -e "$EXT_BACKUP" ]; then
      mv -- "$EXT_BACKUP" "$EXT_DIR" || rollback_failed=1
    fi
    systemctl --user daemon-reload >/dev/null 2>&1 || rollback_failed=1
    if [ "$PRIOR_DAEMON_ENABLED" = "1" ]; then
      systemctl --user enable browser-memory-daemon.service >/dev/null 2>&1 || rollback_failed=1
    else
      systemctl --user disable browser-memory-daemon.service >/dev/null 2>&1 || rollback_failed=1
    fi
    if [ "$PRIOR_WORKER_ENABLED" = "1" ]; then
      systemctl --user enable browser-memory-media-worker.service >/dev/null 2>&1 || rollback_failed=1
    else
      systemctl --user disable browser-memory-media-worker.service >/dev/null 2>&1 || rollback_failed=1
    fi
    if [ "$PRIOR_DAEMON_ACTIVE" = "1" ]; then
      systemctl --user restart browser-memory-daemon.service >/dev/null 2>&1 || rollback_failed=1
      systemctl --user is-active --quiet browser-memory-daemon.service || rollback_failed=1
    else
      systemctl --user stop browser-memory-daemon.service >/dev/null 2>&1 || rollback_failed=1
    fi
    if [ "$PRIOR_WORKER_ACTIVE" = "1" ]; then
      systemctl --user restart browser-memory-media-worker.service >/dev/null 2>&1 || rollback_failed=1
      systemctl --user is-active --quiet browser-memory-media-worker.service || rollback_failed=1
    else
      systemctl --user stop browser-memory-media-worker.service >/dev/null 2>&1 || rollback_failed=1
    fi
    if [ "$rollback_failed" = "1" ]; then
      echo "ROLLBACK INCOMPLETE: prior artifacts were restored where possible, but prior service readiness was not recovered." >&2
      cleanup_install_stage
      exit 70
    fi
    echo "Rollback completed; prior artifacts and service state are active." >&2
  else
    echo "Install failed before publication; installed artifacts were not changed." >&2
  fi
  cleanup_install_stage
  exit "$rc"
}

trap rollback_install ERR
trap cleanup_install_stage EXIT

mkdir -p "$STAGE_ROOT/backups"
chmod 700 "$STAGE_ROOT" "$STAGE_ROOT/backups"
for spec in \
  "$TOKEN_FILE:token" \
  "$ENV_FILE:env" \
  "$UNIT_FILE:daemon-unit" \
  "$WORKER_UNIT_FILE:worker-unit"; do
  target="${spec%:*}"
  name="${spec##*:}"
  if [ -e "$target" ]; then
    cp -a -- "$target" "$STAGE_ROOT/backups/$name"
  else
    : > "$STAGE_ROOT/backups/$name.absent"
  fi
done

if systemctl --user is-active --quiet browser-memory-daemon.service; then PRIOR_DAEMON_ACTIVE=1; fi
if systemctl --user is-active --quiet browser-memory-media-worker.service; then PRIOR_WORKER_ACTIVE=1; fi
if systemctl --user is-enabled --quiet browser-memory-daemon.service; then PRIOR_DAEMON_ENABLED=1; fi
if systemctl --user is-enabled --quiet browser-memory-media-worker.service; then PRIOR_WORKER_ENABLED=1; fi

if [ "${BMD_ROTATE_TOKEN:-0}" = "1" ] || [ ! -s "$TOKEN_FILE" ]; then
  umask 077
  "$PY" - <<'PY' > "$STAGE_ROOT/token"
import secrets
print(secrets.token_urlsafe(48))
PY
else
  cp -- "$TOKEN_FILE" "$STAGE_ROOT/token"
fi
chmod 600 "$STAGE_ROOT/token"
TOKEN="$(tr -d '\r\n' < "$STAGE_ROOT/token")"
if [ -z "$TOKEN" ]; then
  echo "Staged token is empty" >&2
  false
fi

umask 077
cat > "$STAGE_ROOT/env" <<EOF
BMD_HOST=$HOST
BMD_PORT=$PORT
BMD_API_TOKEN=$TOKEN
BMD_POLICY_MODE=$POLICY_MODE
BMD_BLOB_ROOT=$BLOB_DIR
BMD_DERIVATIVE_ROOT=$DERIVATIVE_DIR
BMD_MEDIA_ROOT=$MEDIA_DIR
BMD_MEDIA_SPOOL_ROOT=$MEDIA_SPOOL_DIR
BMD_MAX_MEDIA_SPOOL_BYTES=$MAX_MEDIA_SPOOL_BYTES
BMD_MAX_MEDIA_INFLIGHT_BYTES=$MAX_MEDIA_INFLIGHT_BYTES
BMD_MAX_MEDIA_CONCURRENT_REQUESTS=$MAX_MEDIA_CONCURRENT_REQUESTS
BMD_MEDIA_ROOT_IDENTITY=$MEDIA_ROOT_IDENTITY
BMD_REQUIRE_BLOB_ROOT_MOUNT=$REQUIRE_BLOB_ROOT_MOUNT
BMD_REQUIRE_MEDIA_ROOT_MOUNT=$REQUIRE_MEDIA_ROOT_MOUNT
BMD_MEDIA_WORKER_INTERVAL=${BMD_MEDIA_WORKER_INTERVAL:-30}
BMD_MEDIA_WORKER_LIMIT=${BMD_MEDIA_WORKER_LIMIT:-25}
PYTHONPATH=$ROOT/daemon/src
EOF
chmod 600 "$STAGE_ROOT/env"

cat > "$STAGE_ROOT/daemon-unit" <<EOF
[Unit]
Description=Browser Memory Daemon
Documentation=file:$ROOT/README.md

[Service]
Type=simple
WorkingDirectory=$ROOT
EnvironmentFile=%h/.config/browser-memory-daemon/env
ExecStart=$PY -m browser_memory_daemon --host \${BMD_HOST} --port \${BMD_PORT} serve
Restart=on-failure
RestartSec=2
UMask=0077
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
chmod 644 "$STAGE_ROOT/daemon-unit"

cat > "$STAGE_ROOT/worker-unit" <<EOF
[Unit]
Description=Browser Memory Media Worker
Documentation=file:$ROOT/README.md
After=browser-memory-daemon.service

[Service]
Type=simple
WorkingDirectory=$ROOT
EnvironmentFile=%h/.config/browser-memory-daemon/env
ExecStart=$PY -m browser_memory_daemon media-worker --loop --interval \${BMD_MEDIA_WORKER_INTERVAL} --limit \${BMD_MEDIA_WORKER_LIMIT}
Restart=on-failure
RestartSec=5
UMask=0077
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
chmod 644 "$STAGE_ROOT/worker-unit"

(
  cd "$ROOT/extension"
  npm run build
)

cp -a "$ROOT/extension/dist/." "$EXT_STAGE/"

"$PY" - "$STAGE_ROOT/token" "$EXT_STAGE" "$POLICY_MODE" <<'PY'
from pathlib import Path
import json
import sys

token = Path(sys.argv[1]).read_text().strip()
ext_dir = Path(sys.argv[2])
policy_mode = sys.argv[3]
files = [
    ext_dir / "src" / "config_store.js",
    ext_dir / "src" / "options.js",
    ext_dir / "src" / "popup.js",
]
for path in files:
    text = path.read_text()
    token_needle = "apiToken: '',"
    token_replacement = "apiToken: " + json.dumps(token) + ","
    if token_needle in text:
        text = text.replace(token_needle, token_replacement, 1)
    elif token_replacement not in text:
        raise SystemExit(f"Could not patch apiToken default in {path}")
    mode_needle = "policyMode: 'all'"
    mode_replacement = "policyMode: " + json.dumps(policy_mode)
    if mode_needle in text:
        text = text.replace(mode_needle, mode_replacement, 1)
    elif mode_replacement not in text:
        raise SystemExit(f"Could not patch policyMode default in {path}")
    path.write_text(text)
PY

"$PY" - "$EXT_STAGE" "$STAGE_ROOT" <<'PY'
from pathlib import Path
import hashlib
import json
import shutil
import sys

extension = Path(sys.argv[1]).resolve(strict=True)
stage_root = Path(sys.argv[2]).resolve(strict=True)
manifest = extension / "manifest.json"
required = (
    manifest,
    extension / "src" / "service_worker.js",
    extension / "src" / "config_store.js",
    extension / "src" / "options.js",
    extension / "src" / "popup.js",
)
for path in required:
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"staged extension file missing or empty: {path.name}")
payload = json.loads(manifest.read_text(encoding="utf-8"))
if int(payload.get("manifest_version", 0)) != 3:
    raise SystemExit("staged extension manifest must use Manifest V3")
source_bytes = sum(path.stat().st_size for path in extension.rglob("*") if path.is_file())
required_free = max(16 * 1024 * 1024, source_bytes * 2)
if shutil.disk_usage(extension.parent).free < required_free:
    raise SystemExit("insufficient extension-destination headroom for staged install and rollback")
evidence = {
    "schema_version": 1,
    "extension_files": sum(1 for path in extension.rglob("*") if path.is_file()),
    "extension_bytes": source_bytes,
    "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
}
(stage_root / "artifact-evidence.json").write_text(
    json.dumps(evidence, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

if [ -f "$DATA_DIR/browser-memory.sqlite3" ]; then
  trap - ERR
  set +e
  BMD_API_TOKEN="$TOKEN" BMD_BLOB_ROOT="$BLOB_DIR" BMD_DERIVATIVE_ROOT="$DERIVATIVE_DIR" \
    BMD_MEDIA_ROOT="$MEDIA_DIR" BMD_MEDIA_SPOOL_ROOT="$MEDIA_SPOOL_DIR" \
    BMD_REQUIRE_BLOB_ROOT_MOUNT="$REQUIRE_BLOB_ROOT_MOUNT" \
    BMD_REQUIRE_MEDIA_ROOT_MOUNT="$REQUIRE_MEDIA_ROOT_MOUNT" \
    BMD_MEDIA_ROOT_IDENTITY="$MEDIA_ROOT_IDENTITY" \
    PYTHONPATH="$ROOT/daemon/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$PY" -m browser_memory_daemon --host "$HOST" --port "$PORT" --policy-mode "$POLICY_MODE" migrate --check \
    > "$STAGE_ROOT/migration-check.json"
  migration_rc=$?
  set -e
  trap rollback_install ERR
  if [ "$migration_rc" -ne 0 ]; then
    echo "Database schema preflight failed or has pending migrations (exit $migration_rc); run migrate explicitly before install." >&2
    false
  fi
fi

publish_file() {
  local staged="$1"
  local target="$2"
  local mode="$3"
  local temporary="${target}.install.$$"
  install -m "$mode" "$staged" "$temporary"
  mv -f -- "$temporary" "$target"
}

PUBLISH_STARTED=1
publish_file "$STAGE_ROOT/token" "$TOKEN_FILE" 600
publish_file "$STAGE_ROOT/env" "$ENV_FILE" 600
publish_file "$STAGE_ROOT/daemon-unit" "$UNIT_FILE" 644
publish_file "$STAGE_ROOT/worker-unit" "$WORKER_UNIT_FILE" 644
if [ -e "$EXT_DIR" ]; then
  mv -- "$EXT_DIR" "$EXT_BACKUP"
fi
mv -- "$EXT_STAGE" "$EXT_DIR"
EXT_STAGE=""
EXT_PUBLISHED=1

systemctl --user daemon-reload
systemctl --user enable browser-memory-daemon.service >/dev/null
systemctl --user restart browser-memory-daemon.service
systemctl --user is-active --quiet browser-memory-daemon.service

"$PY" - <<PY
import time
import urllib.error
import urllib.request
url = "http://$HOST:$PORT/health"
last_error = None
for _ in range(40):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            body = response.read().decode("utf-8")
            if response.status != 200:
                raise SystemExit(f"health failed: {response.status} {body}")
            break
    except urllib.error.URLError as exc:
        last_error = exc
        time.sleep(0.25)
else:
    raise SystemExit(f"health failed: {last_error}")
print("WSL health OK:", body)
PY

systemctl --user enable browser-memory-media-worker.service >/dev/null
systemctl --user restart browser-memory-media-worker.service
systemctl --user is-active --quiet browser-memory-media-worker.service

if [ -x "$PS" ]; then
  "$PS" -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:$PORT/health' -TimeoutSec 5 | ConvertTo-Json -Compress } catch { Write-Error \$_; exit 1 }" \
    | sed 's/^/Windows health OK: /'
else
  echo "Windows PowerShell not found at $PS; skipped Windows loopback health check" >&2
fi

mkdir -p "$STATE_DIR/install-history"
chmod 700 "$STATE_DIR/install-history"
"$PY" - "$STAGE_ROOT/artifact-evidence.json" "$STATE_DIR/install-history" "$UNIT_FILE" "$WORKER_UNIT_FILE" "$ENV_FILE" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sys

evidence = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
history = Path(sys.argv[2])
paths = [Path(value) for value in sys.argv[3:]]
evidence.update(
    {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "result": "ready",
        "published_files": [
            {
                "name": path.name,
                "mode": oct(path.stat().st_mode & 0o777),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in paths
        ],
    }
)
destination = history / f"install-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}.json"
destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
destination.chmod(0o600)
PY

trap - ERR
if [ -e "$EXT_BACKUP" ]; then
  rm -rf -- "$EXT_BACKUP"
fi

cat <<EOF
Daily-driver assets installed.

Extension directory:
  $(wslpath -w "$EXT_DIR" 2>/dev/null || printf '%s' "$EXT_DIR")

Policy mode:
  $POLICY_MODE

WSL services:
  systemctl --user status browser-memory-daemon.service
  systemctl --user status browser-memory-media-worker.service
  journalctl --user -u browser-memory-daemon.service -f
  journalctl --user -u browser-memory-media-worker.service -f

Aggregate health snapshot:
  $ROOT/scripts/daily-driver-health.sh

Chrome manual load/reload step still required by Chrome:
  chrome://extensions → Browser Memory Daemon → Reload
EOF
