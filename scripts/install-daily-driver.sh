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

Install/refresh writes protected WSL config, systemd user units, and the
Windows-local unpacked extension artifact, then restarts services.

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
  - build extension/dist, copy it to the Windows-local artifact dir, and patch token/policy defaults there;
  - daemon-reload, enable/restart both user services, then verify WSL and Windows loopback health.

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

mkdir -p "$CFG_DIR" "$DATA_DIR" "$DERIVATIVE_DIR" "$STATE_DIR" "$UNIT_DIR" "$EXT_DIR"
chmod 700 "$CFG_DIR"

if [ "${BMD_ROTATE_TOKEN:-0}" = "1" ] || [ ! -s "$TOKEN_FILE" ]; then
  umask 077
  "$PY" - <<'PY' > "$TOKEN_FILE"
import secrets
print(secrets.token_urlsafe(48))
PY
fi
chmod 600 "$TOKEN_FILE"

TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
if [ -z "$TOKEN" ]; then
  echo "Token file is empty: $TOKEN_FILE" >&2
  exit 1
fi

umask 077
cat > "$ENV_FILE" <<EOF
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
chmod 600 "$ENV_FILE"

cat > "$UNIT_FILE" <<EOF
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
chmod 644 "$UNIT_FILE"

cat > "$WORKER_UNIT_FILE" <<EOF
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
chmod 644 "$WORKER_UNIT_FILE"

(
  cd "$ROOT/extension"
  npm run build
)

find "$EXT_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -a "$ROOT/extension/dist/." "$EXT_DIR/"

"$PY" - "$TOKEN_FILE" "$EXT_DIR" "$POLICY_MODE" <<'PY'
from pathlib import Path
import json
import sys

token = Path(sys.argv[1]).read_text().strip()
ext_dir = Path(sys.argv[2])
policy_mode = sys.argv[3]
files = [
    ext_dir / "src" / "service_worker.js",
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

systemctl --user daemon-reload
systemctl --user enable --now browser-memory-daemon.service browser-memory-media-worker.service >/dev/null
systemctl --user restart browser-memory-daemon.service browser-memory-media-worker.service
systemctl --user is-active --quiet browser-memory-daemon.service
systemctl --user is-active --quiet browser-memory-media-worker.service

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

if [ -x "$PS" ]; then
  "$PS" -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:$PORT/health' -TimeoutSec 5 | ConvertTo-Json -Compress } catch { Write-Error \$_; exit 1 }" \
    | sed 's/^/Windows health OK: /'
else
  echo "Windows PowerShell not found at $PS; skipped Windows loopback health check" >&2
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
