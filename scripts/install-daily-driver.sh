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
HOST="${BMD_HOST:-127.0.0.1}"
PORT="${BMD_PORT:-8765}"
PS="${BMD_POWERSHELL:-/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe}"

if [ ! -x "$PY" ]; then
  echo "Python runtime not executable: $PY" >&2
  exit 1
fi

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

(
  cd "$ROOT/extension"
  npm run build
)

find "$EXT_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -a "$ROOT/extension/dist/." "$EXT_DIR/"

"$PY" - "$TOKEN_FILE" "$EXT_DIR" <<'PY'
from pathlib import Path
import json
import sys

token = Path(sys.argv[1]).read_text().strip()
ext_dir = Path(sys.argv[2])
files = [
    ext_dir / "src" / "service_worker.js",
    ext_dir / "src" / "options.js",
    ext_dir / "src" / "popup.js",
]
for path in files:
    text = path.read_text()
    needle = "apiToken: '',"
    replacement = "apiToken: " + json.dumps(token) + ","
    if needle in text:
        path.write_text(text.replace(needle, replacement, 1))
    elif replacement in text:
        continue
    else:
        raise SystemExit(f"Could not patch apiToken default in {path}")
PY

systemctl --user daemon-reload
systemctl --user enable --now browser-memory-daemon.service >/dev/null
systemctl --user restart browser-memory-daemon.service
sleep 1
systemctl --user is-active --quiet browser-memory-daemon.service

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

WSL service:
  systemctl --user status browser-memory-daemon.service
  journalctl --user -u browser-memory-daemon.service -f

Chrome manual load step still required by Chrome:
  chrome://extensions → Developer mode → Load unpacked → select the extension directory above
EOF
