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

TMP_ROOT="$(mktemp -d /tmp/browser-memory-fast-gate.XXXXXX)"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p \
  "$TMP_ROOT/home" \
  "$TMP_ROOT/tmp" \
  "$TMP_ROOT/default-xdg/config" \
  "$TMP_ROOT/default-xdg/data" \
  "$TMP_ROOT/default-xdg/state" \
  "$TMP_ROOT/default-xdg/cache" \
  "$TMP_ROOT/mypy-cache"

export HOME="$TMP_ROOT/home"
export TMPDIR="$TMP_ROOT/tmp"
export XDG_CONFIG_HOME="$TMP_ROOT/default-xdg/config"
export XDG_DATA_HOME="$TMP_ROOT/default-xdg/data"
export XDG_STATE_HOME="$TMP_ROOT/default-xdg/state"
export XDG_CACHE_HOME="$TMP_ROOT/default-xdg/cache"
export COVERAGE_FILE="$TMP_ROOT/.coverage"
export BMD_PYTHON="$PY"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
COVERAGE_JSON="${BMD_COVERAGE_JSON:-$TMP_ROOT/coverage.json}"

QUALITY_PATHS=(
  daemon/src/browser_memory_daemon/migrations.py
  daemon/src/browser_memory_daemon/migration_steps
  daemon/src/browser_memory_daemon/storage_paths.py
)

"$PY" -m ruff check --no-cache "${QUALITY_PATHS[@]}"
"$PY" -m mypy --cache-dir "$TMP_ROOT/mypy-cache"
"$PY" -m coverage run -m pytest -q -p no:cacheprovider
"$PY" -m coverage report
"$PY" -m coverage json -o "$COVERAGE_JSON"
(cd extension && npm test)
"$PY" scripts/generate_test_inventory.py --check
./scripts/secret-scan.sh
git diff --check -- .

if find "$TMP_ROOT/default-xdg" -type f -print -quit | read -r unexpected; then
  printf 'fast gate failed: default-XDG write escaped explicit test fixtures: %s\n' "$unexpected" >&2
  exit 1
fi

printf 'FAST_GATE_PASS\n'
printf 'scope: targeted Ruff/mypy; branch coverage; Python/Node tests; catalog/secret/diff checks; default-XDG sentinel\n'
