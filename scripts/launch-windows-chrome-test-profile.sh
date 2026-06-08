#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHROME="/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
if [ ! -x "$CHROME" ]; then
  CHROME="/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe"
fi
if [ ! -x "$CHROME" ]; then
  echo "Chrome not found under Program Files" >&2
  exit 1
fi
PROFILE="${BMD_CHROME_TEST_PROFILE:-/tmp/browser-memory-chrome-profile}"
EXT_DIST="$ROOT/extension/dist"
if [ ! -d "$EXT_DIST" ]; then
  (cd "$ROOT/extension" && npm run build)
fi
"$CHROME" --user-data-dir="$(wslpath -w "$PROFILE")" --disable-first-run-ui --load-extension="$(wslpath -w "$EXT_DIST")" http://127.0.0.1:8765/health >/dev/null 2>&1 &
echo "launched Windows Chrome with isolated profile: $PROFILE"
