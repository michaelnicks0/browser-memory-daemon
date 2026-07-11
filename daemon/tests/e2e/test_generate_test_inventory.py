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

ARCHITECTURE_DOC_TEMPLATE = """# Architecture

<!-- BEGIN GENERATED:requirements-trace -->
stale
<!-- END GENERATED:requirements-trace -->
"""

TEST_PLAN_DOC_TEMPLATE = """# Test Plan

<!-- BEGIN GENERATED:requirement-coverage -->
stale
<!-- END GENERATED:requirement-coverage -->
"""

STATUS_DOC_TEMPLATE = """# Status

<!-- BEGIN GENERATED:requirement-posture -->
stale
<!-- END GENERATED:requirement-posture -->
"""

EXECUTIVE_DOC_TEMPLATE = """# Executive Brief

<!-- BEGIN GENERATED:verification-depth -->
stale
<!-- END GENERATED:verification-depth -->
"""


def load_generator():
    spec = importlib.util.spec_from_file_location("bmd_generate_test_inventory", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def requirement_toml(
    *,
    statement: str = "The system shall capture a synthetic page.",
    revision: int = 1,
    implementation: str = '["daemon/tests/test_sample.py"]',
    integration_evidence: str = '["daemon/tests/test_sample.py::test_sample"]',
    validation_evidence: str = '["daemon/tests/test_sample.py::test_sample"]',
) -> str:
    return f'''schema_version = 1
catalog_revision = 1

[[requirements]]
id = "REQ-001"
revision = {revision}
statement = "{statement}"
rationale = "Synthetic catalog fixture."
owner = "Test fixture"
status = "active"
aliases = ["HRD-999"]
implementation = {implementation}
unit_evidence = []
integration_evidence = {integration_evidence}
system_evidence = ["scripts/run-e2e.sh"]
operational_evidence = ["docs/test-plan.md"]
validation_evidence = {validation_evidence}

[[legacy_aliases]]
source = "fixture"
legacy_id = "REQ-OLD"
canonical_ids = ["REQ-001"]
disposition = "superseded"
reason = "Synthetic legacy alias fixture."
'''


def write_fixture_root(tmp_path: Path, *, catalog_text: str | None = None) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "requirements").mkdir()
    (tmp_path / "scripts").mkdir()
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
    (tmp_path / "scripts/run-e2e.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (tmp_path / "requirements/catalog.toml").write_text(
        catalog_text or requirement_toml(),
        encoding="utf-8",
    )
    (tmp_path / "docs/TESTS.md").write_text(TEST_DOC_TEMPLATE, encoding="utf-8")
    (tmp_path / "docs/ARCHITECTURE.md").write_text(ARCHITECTURE_DOC_TEMPLATE, encoding="utf-8")
    (tmp_path / "docs/test-plan.md").write_text(TEST_PLAN_DOC_TEMPLATE, encoding="utf-8")
    (tmp_path / "docs/STATUS.md").write_text(STATUS_DOC_TEMPLATE, encoding="utf-8")
    (tmp_path / "docs/EXECUTIVE_BRIEF.md").write_text(EXECUTIVE_DOC_TEMPLATE, encoding="utf-8")
    return tmp_path


def write_rendered_docs(generator, root: Path, inventory) -> None:
    for path, rendered in generator.render_repository_docs(root, inventory).items():
        path.write_text(rendered, encoding="utf-8")


def test_generate_test_inventory_reports_catalog_traceability_success(tmp_path):
    generator = load_generator()
    root = write_fixture_root(tmp_path)

    inventory = generator.build_inventory(root)

    assert inventory.total_cases == 2
    assert inventory.traceability.ok is True
    assert inventory.traceability.catalog_requirements == ["REQ-001"]
    assert inventory.traceability.active_requirements == ["REQ-001"]
    assert inventory.traceability.planned_requirements == []
    rendered = generator.render_repository_docs(root, inventory)
    assert "Traceability gate: **✅ pass**" in rendered[root / "docs/TESTS.md"]
    assert "Static test inventory measured | 2 tests / 2 files" in rendered[root / "docs/TESTS.md"]
    assert "The system shall capture a synthetic page." in rendered[root / "docs/ARCHITECTURE.md"]
    assert "Legacy alias reconciliation" in rendered[root / "docs/ARCHITECTURE.md"]
    assert "`REQ-OLD`" in rendered[root / "docs/ARCHITECTURE.md"]
    assert "`daemon/tests/test_sample.py::test_sample`" in rendered[root / "docs/test-plan.md"]
    assert "1 active" in rendered[root / "docs/STATUS.md"]
    assert "2 static test functions" in rendered[root / "docs/EXECUTIVE_BRIEF.md"]


def test_generate_test_inventory_check_fails_for_catalog_gaps(tmp_path):
    generator = load_generator()
    root = write_fixture_root(
        tmp_path,
        catalog_text=requirement_toml(
            implementation='["daemon/tests/missing.py"]',
            integration_evidence='["daemon/tests/test_sample.py::test_missing"]',
            validation_evidence="[]",
        ),
    )
    inventory = generator.build_inventory(root)
    write_rendered_docs(generator, root, inventory)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--root", str(root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "REQ-001 -> daemon/tests/missing.py" in result.stderr
    assert "REQ-001 -> daemon/tests/test_sample.py::test_missing" in result.stderr
    assert "active requirements without validation evidence: REQ-001" in result.stderr


def test_catalog_rejects_duplicate_ids(tmp_path):
    generator = load_generator()
    duplicate_entry = requirement_toml().split("[[requirements]]", 1)[1]
    root = write_fixture_root(
        tmp_path,
        catalog_text=requirement_toml() + "\n[[requirements]]" + duplicate_entry,
    )

    inventory = generator.build_inventory(root)

    assert inventory.traceability.ok is False
    assert inventory.traceability.duplicate_requirement_ids == ["REQ-001"]


def test_catalog_statement_change_requires_revision_increment(tmp_path):
    generator = load_generator()
    root = write_fixture_root(tmp_path)
    inventory = generator.build_inventory(root)
    previous = generator.parse_catalog_text(requirement_toml(statement="The system shall keep the original statement.", revision=1))

    unchanged_revision = generator.parse_catalog_text(
        requirement_toml(statement="The system shall use a changed statement.", revision=1)
    )
    changed_report = generator.validate_catalog(root, unchanged_revision, inventory, previous_catalog=previous)
    assert changed_report.normative_revision_errors == ["REQ-001"]

    incremented_revision = generator.parse_catalog_text(
        requirement_toml(statement="The system shall use a changed statement.", revision=2)
    )
    incremented_report = generator.validate_catalog(root, incremented_revision, inventory, previous_catalog=previous)
    assert incremented_report.normative_revision_errors == []