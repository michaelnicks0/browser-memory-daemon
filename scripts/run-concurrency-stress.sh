#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -n "${BMD_PYTHON:-}" ]; then
  PY="$BMD_PYTHON"
elif command -v python3.11 >/dev/null 2>&1; then
  PY=python3.11
else
  PY=python3
fi

export PYTHONPATH="$ROOT/daemon/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m browser_memory_daemon.concurrency_stress "$@"
