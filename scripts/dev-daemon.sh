#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/daemon/src${PYTHONPATH:+:$PYTHONPATH}"
export BMD_API_TOKEN="${BMD_API_TOKEN:-dev-token}"
export BMD_HOST="${BMD_HOST:-127.0.0.1}"
export BMD_PORT="${BMD_PORT:-8765}"
python3 -m browser_memory_daemon --host "$BMD_HOST" --port "$BMD_PORT" --token "$BMD_API_TOKEN" serve
