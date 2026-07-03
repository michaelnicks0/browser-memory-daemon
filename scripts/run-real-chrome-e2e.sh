#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

choose_port_base() {
  local attempt base
  for attempt in $(seq 1 200); do
    base=$((22000 + (RANDOM % 8000)))
    if ! "${BMD_PYTHON:-python3}" - "$base" <<'PY'
import socket
import sys

base = int(sys.argv[1])
for port in (base, base + 1, base + 2):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.05)
    try:
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit(1)
    finally:
        sock.close()
PY
    then
      continue
    fi
    if [ -x /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe ]; then
      if ! /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command '
param([int]$base)
foreach ($p in @($base, ($base + 1), ($base + 2))) {
  if (Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue) { exit 1 }
}
' "$base" >/dev/null; then
        continue
      fi
    fi
    printf '%s\n' "$base"
    return 0
  done
  echo "could not find three adjacent free loopback ports" >&2
  return 1
}

(cd extension && npm run build)
if [ -n "${BMD_REAL_CHROME_POLICY_MODE:-}" ]; then
  node scripts/real-chrome-e2e.mjs
else
  index=0
  for mode in ${BMD_REAL_CHROME_MATRIX_MODES:-all strict}; do
    echo "[real-chrome-e2e-matrix] mode=$mode"
    if [ -z "${BMD_REAL_CHROME_PORT_BASE:-}${BMD_REAL_CHROME_DAEMON_PORT:-}${BMD_REAL_CHROME_PAGE_PORT:-}${BMD_REAL_CHROME_CDP_PORT:-}" ]; then
      BMD_REAL_CHROME_MATRIX_INDEX="$index" BMD_REAL_CHROME_PORT_BASE="$(BMD_REAL_CHROME_MATRIX_INDEX="$index" choose_port_base)" BMD_REAL_CHROME_POLICY_MODE="$mode" node scripts/real-chrome-e2e.mjs
    else
      BMD_REAL_CHROME_POLICY_MODE="$mode" node scripts/real-chrome-e2e.mjs
    fi
    index=$((index + 1))
  done
fi
