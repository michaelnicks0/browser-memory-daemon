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

CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/browser-memory-daemon"
ENV_FILE="${BMD_ENV_FILE:-$CFG_DIR/env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi
TOKEN_FILE="${BMD_TOKEN_FILE:-$CFG_DIR/token}"
if [ ! -s "$TOKEN_FILE" ]; then
  echo "Browser Memory Daemon token file missing or empty: $TOKEN_FILE" >&2
  exit 1
fi
TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"

WIN_USER="${BMD_WINDOWS_USER:-${USER:-${LOGNAME:-}}}"
EXT_DIR="${BMD_WINDOWS_EXTENSION_DIR:-}"
if [ -z "$EXT_DIR" ] && [ -n "$WIN_USER" ]; then
  EXT_DIR="/mnt/c/Users/${WIN_USER}/AppData/Local/browser-memory-daemon/extension"
fi

ARGS=(daily-driver-health)
if [ -n "$EXT_DIR" ]; then
  ARGS+=(--extension-dir "$EXT_DIR")
fi

cd "$ROOT"
BMD_API_TOKEN="$TOKEN" PYTHONPATH="$ROOT/daemon/src${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m browser_memory_daemon "${ARGS[@]}" "$@"
