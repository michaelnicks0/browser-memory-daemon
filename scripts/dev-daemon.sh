#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/daemon/src${PYTHONPATH:+:$PYTHONPATH}"
export BMD_API_TOKEN="${BMD_API_TOKEN:-dev-token}"
export BMD_HOST="${BMD_HOST:-127.0.0.1}"
export BMD_PORT="${BMD_PORT:-8765}"
if [ -n "${BMD_PYTHON:-}" ]; then
  PY="$BMD_PYTHON"
elif command -v python3.11 >/dev/null 2>&1; then
  PY="$(command -v python3.11)"
else
  PY="$(command -v python3)"
fi
"$PY" -m browser_memory_daemon --host "$BMD_HOST" --port "$BMD_PORT" --token "$BMD_API_TOKEN" serve
