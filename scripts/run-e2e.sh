#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m pytest -q
(cd extension && npm test && npm run build)
if [ "${BMD_SKIP_REAL_CHROME_E2E:-0}" != "1" ]; then
  ./scripts/run-real-chrome-e2e.sh
fi
./scripts/secret-scan.sh
git diff --check -- .
