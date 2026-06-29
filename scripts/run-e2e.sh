#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [ -n "${BMD_PYTHON:-}" ]; then
  PY="$BMD_PYTHON"
elif command -v python3.11 >/dev/null 2>&1; then
  PY="$(command -v python3.11)"
else
  PY="$(command -v python3)"
fi
"$PY" -m pytest -q
(cd extension && npm test && npm run build)
if [ "${BMD_SKIP_REAL_CHROME_E2E:-0}" != "1" ]; then
  ./scripts/run-real-chrome-e2e.sh
fi
./scripts/secret-scan.sh
git diff --check -- .
