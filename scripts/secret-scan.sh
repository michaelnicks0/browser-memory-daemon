#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$ROOT" <<'PY'
from pathlib import Path
import re
import sys
root = Path(sys.argv[1])
patterns = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{30,}", re.I),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
ignored = {'.git', 'node_modules', 'dist', '__pycache__', '.pytest_cache'}
violations = []
for path in root.rglob('*'):
    if any(part in ignored for part in path.parts):
        continue
    if not path.is_file():
        continue
    try:
        text = path.read_text(errors='ignore')
    except Exception:
        continue
    for pattern in patterns:
        if pattern.search(text):
            violations.append(str(path.relative_to(root)))
            break
if violations:
    print('secret-shaped content found:', violations)
    raise SystemExit(1)
print('secret scan passed')
PY
