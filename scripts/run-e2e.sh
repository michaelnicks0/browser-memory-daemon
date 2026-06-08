#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m pytest -q
(cd extension && npm test && npm run build)
./scripts/secret-scan.sh
git diff --check -- .
