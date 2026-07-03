#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [ -n "${BMD_PYTHON:-}" ]; then
  PYTHON="$BMD_PYTHON"
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON="python3.11"
else
  PYTHON="python3"
fi
PYTHONPATH="$ROOT/daemon/src${PYTHONPATH:+:$PYTHONPATH}" exec "$PYTHON" -m browser_memory_daemon.performance_benchmarks "$@"
