from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "generate_test_inventory.py"

TEST_DOC_TEMPLATE = """# Tests

<!-- BEGIN GENERATED:inventory-summary -->
stale
<!-- END GENERATED:inventory-summary -->

<!-- BEGIN GENERATED:audit-run -->
stale
<!-- END GENERATED:audit-run -->

<!-- BEGIN GENERATED:traceability-gate -->
stale
<!-- END GENERATED:traceability-gate -->

<!-- BEGIN GENERATED:per-file-counts -->
stale
<!-- END GENERATED:per-file-counts -->

<!-- BEGIN GENERATED:test-case-inventory -->
stale
<!-- END GENERATED:test-case-inventory -->
"""


def load_generator():
    spec = importlib.util.spec_from_file_location("bmd_generate_test_inventory", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_fixture_root(tmp_path: Path, *, test_plan_rows: str, architecture_rows: str) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "daemon/tests").mkdir(parents=True)
    (tmp_path / "extension/tests/unit").mkdir(parents=True)
    (tmp_path / "daemon/tests/test_sample.py").write_text(
        "def test_sample():\n    assert True\n",
        encoding="utf-8",
    )
    (tmp_path / "extension/tests/unit/sample.test.js").write_text(
        "test('sample node test', () => {});\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/ARCHITECTURE.md").write_text(
        "# Architecture\n\n| Requirement | Need | Impl | Verification |\n|---|---|---|---|\n"
        + architecture_rows,
        encoding="utf-8",
    )
    (tmp_path / "docs/test-plan.md").write_text(
        "# Test Plan\n\n| Requirement | Test evidence |\n|---|---|\n" + test_plan_rows,
        encoding="utf-8",
    )
    return tmp_path


def test_generate_test_inventory_reports_traceability_success(tmp_path):
    generator = load_generator()
    root = write_fixture_root(
        tmp_path,
        architecture_rows="| REQ-001 | Capture | `daemon/tests/test_sample.py` | pytest |\n",
        test_plan_rows="| REQ-001 capture | `daemon/tests/test_sample.py`; `extension/tests/unit/sample.test.js` |\n",
    )

    inventory = generator.build_inventory(root)

    assert inventory.total_cases == 2
    assert inventory.traceability.ok is True
    assert inventory.traceability.missing_test_plan_requirements == []
    rendered = generator.render_doc(TEST_DOC_TEMPLATE, inventory)
    assert "Traceability gate: **✅ pass**" in rendered
    assert "Static test inventory measured | 2 tests / 2 files" in rendered


def test_generate_test_inventory_check_fails_for_traceability_gaps(tmp_path):
    generator = load_generator()
    root = write_fixture_root(
        tmp_path,
        architecture_rows=(
            "| REQ-001 | Capture | `daemon/tests/test_sample.py` | pytest |\n"
            "| REQ-002 | Storage | `daemon/tests/missing_test.py` | pytest |\n"
        ),
        test_plan_rows="| REQ-001 capture | `daemon/tests/missing_test.py` |\n",
    )
    inventory = generator.build_inventory(root)
    (root / "docs/TESTS.md").write_text(generator.render_doc(TEST_DOC_TEMPLATE, inventory), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--root", str(root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "REQ-002" in result.stderr
    assert "daemon/tests/missing_test.py" in result.stderr
