#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${BMD_PYTHON:-$(command -v python3)}"
WIN_USER="${BMD_WINDOWS_USER:-user}"
EXT_DIR="${BMD_WINDOWS_EXTENSION_DIR:-/mnt/c/Users/${WIN_USER}/AppData/Local/browser-memory-daemon/extension}"
CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/browser-memory-daemon"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/browser-memory-daemon"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/browser-memory-daemon"
UNIT_DIR="$HOME/.config/systemd/user"
TOKEN_FILE="$CFG_DIR/token"
ENV_FILE="$CFG_DIR/env"
UNIT_FILE="$UNIT_DIR/browser-memory-daemon.service"
WORKER_UNIT_FILE="$UNIT_DIR/browser-memory-media-worker.service"
HOST="${BMD_HOST:-127.0.0.1}"
PORT="${BMD_PORT:-8765}"
POLICY_MODE="${BMD_POLICY_MODE:-all}"
PS="${BMD_POWERSHELL:-/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe}"

if [ ! -x "$PY" ]; then
  echo "Python runtime not executable: $PY" >&2
  exit 1
fi

case "$POLICY_MODE" in
  all|recall|balanced|strict) ;;
  *) echo "BMD_POLICY_MODE must be one of: all, recall, balanced, strict" >&2; exit 1 ;;
esac

mkdir -p "$CFG_DIR" "$DATA_DIR" "$STATE_DIR" "$UNIT_DIR" "$EXT_DIR"
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
BMD_MEDIA_WORKER_INTERVAL=${BMD_MEDIA_WORKER_INTERVAL:-30}
BMD_MEDIA_WORKER_LIMIT=${BMD_MEDIA_WORKER_LIMIT:-25}
PYTHONPATH=$ROOT/daemon/src
EOF
chmod 600 "$ENV_FILE"

cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Browser Memory Daemon
Documentation=file:$ROOT/README.md
After=default.target

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
sleep 1
systemctl --user is-active --quiet browser-memory-daemon.service
systemctl --user is-active --quiet browser-memory-media-worker.service

"$PY" - <<PY
import urllib.request
url = "http://$HOST:$PORT/health"
with urllib.request.urlopen(url, timeout=5) as response:
    body = response.read().decode("utf-8")
    if response.status != 200:
        raise SystemExit(f"health failed: {response.status} {body}")
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

Chrome manual load/reload step still required by Chrome:
  chrome://extensions → Browser Memory Daemon → Reload
EOF
