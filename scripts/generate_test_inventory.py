#!/usr/bin/env python3
"""Generate docs/TESTS.md inventory from daemon pytest and extension node:test sources.

The inventory is static and body-safe: it parses test names, source paths, and line
numbers without executing browser captures or reading runtime data. It counts Python
``test_*`` functions/methods and top-level JavaScript ``test(...)`` registrations.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from collections.abc import Callable
import html
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

TARGET_DOC = Path("docs/TESTS.md")
CATALOG_PATH = Path("requirements/catalog.toml")
REGION_IDS = ("inventory-summary", "audit-run", "traceability-gate", "per-file-counts", "test-case-inventory")
REQ_ID_RE = re.compile(r"^REQ-\d{3}$")
VALID_REQUIREMENT_STATUSES = {"active", "planned", "deprecated", "superseded"}
EVIDENCE_FIELDS = (
    "unit_evidence",
    "integration_evidence",
    "system_evidence",
    "operational_evidence",
    "validation_evidence",
)


@dataclass
class Requirement:
    id: str
    revision: int
    statement: str
    rationale: str
    owner: str
    status: str
    aliases: list[str] = field(default_factory=list)
    implementation: list[str] = field(default_factory=list)
    unit_evidence: list[str] = field(default_factory=list)
    integration_evidence: list[str] = field(default_factory=list)
    system_evidence: list[str] = field(default_factory=list)
    operational_evidence: list[str] = field(default_factory=list)
    validation_evidence: list[str] = field(default_factory=list)


@dataclass
class LegacyAlias:
    source: str
    legacy_id: str
    canonical_ids: list[str]
    disposition: str
    reason: str


@dataclass
class RequirementCatalog:
    schema_version: int
    catalog_revision: int
    requirements: list[Requirement]
    legacy_aliases: list[LegacyAlias] = field(default_factory=list)


@dataclass
class TestCase:
    file: str
    platform: str
    suite: str
    name: str
    line: int
    note: str


@dataclass
class FileEntry:
    file: str
    platform: str
    classes: int = 0
    cases: list[TestCase] = field(default_factory=list)


@dataclass
class TraceabilityReport:
    ok: bool
    catalog_requirements: list[str]
    active_requirements: list[str]
    planned_requirements: list[str]
    duplicate_requirement_ids: list[str]
    invalid_requirement_definitions: list[str]
    duplicate_aliases: list[str]
    legacy_alias_errors: list[str]
    missing_implementation_paths: list[str]
    unresolved_evidence_references: list[str]
    active_requirements_without_validation: list[str]
    normative_revision_errors: list[str]
    removed_requirement_ids: list[str]
    catalog_load_errors: list[str]
    inventory_files: int
    inventory_cases: int


@dataclass
class Inventory:
    file_count: int
    total_cases: int
    python_cases: int
    node_cases: int
    total_classes: int
    per_file: list[FileEntry]
    catalog: RequirementCatalog | None = None
    traceability: TraceabilityReport | None = None


def _humanize(name: str, docstring: str | None = None) -> str:
    if docstring:
        first = docstring.strip().splitlines()[0].strip()
        if first:
            return first if first[-1:] in ".!?" else first + "."
    cleaned = re.sub(r"^test[_\s-]*", "", name).replace("_", " ").strip()
    if not cleaned:
        cleaned = name.strip()
    return cleaned[:1].upper() + cleaned[1:] + ("" if cleaned[-1:] in ".!?" else ".")


def _escape_cell(value: str) -> str:
    return html.escape(value.replace("\\", "\\\\").replace("|", "\\|"), quote=False)


def _base_names(node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def _is_test_class(node: ast.AST) -> bool:
    if not isinstance(node, ast.ClassDef):
        return False
    bases = _base_names(node)
    return bool(
        node.name.startswith("Test")
        or bases & {"TestCase", "IsolatedAsyncioTestCase", "AsyncTestCase"}
        or any(base.endswith("TestCase") for base in bases)
    )


def _is_module_test(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")


def _is_method_test(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")


def _parse_python_test(path: Path, root: Path) -> FileEntry:
    rel = path.relative_to(root).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    entry = FileEntry(file=rel, platform="pytest")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_module_test(node):
            entry.cases.append(
                TestCase(
                    file=rel,
                    platform="pytest",
                    suite="(module)",
                    name=node.name,
                    line=node.lineno,
                    note=_humanize(node.name, ast.get_docstring(node)),
                )
            )
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and _is_test_class(node):
            methods = [
                m
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_method_test(m)
            ]
            if methods:
                entry.classes += 1
            for method in methods:
                entry.cases.append(
                    TestCase(
                        file=rel,
                        platform="pytest",
                        suite=node.name,
                        name=method.name,
                        line=method.lineno,
                        note=_humanize(method.name, ast.get_docstring(method)),
                    )
                )
    entry.cases.sort(key=lambda case: case.line)
    return entry


_JS_TEST_RE = re.compile(r"^\s*test\(\s*([`'\"])(.*?)\1", re.MULTILINE)


def _parse_node_test(path: Path, root: Path) -> FileEntry:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    entry = FileEntry(file=rel, platform="node:test")
    for match in _JS_TEST_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        name = match.group(2)
        entry.cases.append(
            TestCase(
                file=rel,
                platform="node:test",
                suite="(module)",
                name=name,
                line=line,
                note=_humanize(name),
            )
        )
    return entry


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def parse_catalog_text(text: str) -> RequirementCatalog:
    data = tomllib.loads(text)
    requirements = [
        Requirement(
            id=str(item.get("id", "")).strip(),
            revision=int(item.get("revision", 0)),
            statement=str(item.get("statement", "")).strip(),
            rationale=str(item.get("rationale", "")).strip(),
            owner=str(item.get("owner", "")).strip(),
            status=str(item.get("status", "")).strip(),
            aliases=_string_list(item.get("aliases", [])),
            implementation=_string_list(item.get("implementation", [])),
            unit_evidence=_string_list(item.get("unit_evidence", [])),
            integration_evidence=_string_list(item.get("integration_evidence", [])),
            system_evidence=_string_list(item.get("system_evidence", [])),
            operational_evidence=_string_list(item.get("operational_evidence", [])),
            validation_evidence=_string_list(item.get("validation_evidence", [])),
        )
        for item in data.get("requirements", [])
        if isinstance(item, dict)
    ]
    legacy_aliases = [
        LegacyAlias(
            source=str(item.get("source", "")).strip(),
            legacy_id=str(item.get("legacy_id", "")).strip(),
            canonical_ids=_string_list(item.get("canonical_ids", [])),
            disposition=str(item.get("disposition", "")).strip(),
            reason=str(item.get("reason", "")).strip(),
        )
        for item in data.get("legacy_aliases", [])
        if isinstance(item, dict)
    ]
    return RequirementCatalog(
        schema_version=int(data.get("schema_version", 0)),
        catalog_revision=int(data.get("catalog_revision", 0)),
        requirements=requirements,
        legacy_aliases=legacy_aliases,
    )


def _load_catalog(root: Path) -> tuple[RequirementCatalog, list[str]]:
    path = root / CATALOG_PATH
    try:
        return parse_catalog_text(path.read_text(encoding="utf-8")), []
    except (OSError, tomllib.TOMLDecodeError, TypeError, ValueError) as exc:
        empty = RequirementCatalog(schema_version=0, catalog_revision=0, requirements=[])
        return empty, [f"{CATALOG_PATH}: {exc}"]


def _load_head_catalog(root: Path) -> RequirementCatalog | None:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"HEAD:{CATALOG_PATH.as_posix()}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return parse_catalog_text(result.stdout)
    except (tomllib.TOMLDecodeError, TypeError, ValueError):
        return None


def _test_node_ids(inventory: Inventory) -> set[str]:
    nodes: set[str] = set()
    for entry in inventory.per_file:
        for case in entry.cases:
            if entry.platform == "pytest" and case.suite != "(module)":
                nodes.add(f"{entry.file}::{case.suite}::{case.name}")
            else:
                nodes.add(f"{entry.file}::{case.name}")
    return nodes


def _reference_exists(root: Path, reference: str, test_nodes: set[str]) -> bool:
    path_text, separator, _node = reference.partition("::")
    if not path_text or Path(path_text).is_absolute() or ".." in Path(path_text).parts:
        return False
    if not (root / path_text).exists():
        return False
    return not separator or reference in test_nodes


def validate_catalog(
    root: Path,
    catalog: RequirementCatalog,
    inventory: Inventory,
    *,
    previous_catalog: RequirementCatalog | None = None,
    catalog_load_errors: list[str] | None = None,
) -> TraceabilityReport:
    ids = [requirement.id for requirement in catalog.requirements]
    id_counts = Counter(ids)
    duplicates = sorted(req_id for req_id, count in id_counts.items() if count > 1)
    requirement_ids = set(ids)
    invalid_definitions: list[str] = []
    if catalog.schema_version != 1:
        invalid_definitions.append(f"catalog: unsupported schema_version {catalog.schema_version}")
    if catalog.catalog_revision < 1:
        invalid_definitions.append("catalog: catalog_revision must be >= 1")
    if not catalog.requirements:
        invalid_definitions.append("catalog: at least one requirement is required")
    missing_implementation: list[str] = []
    unresolved_evidence: list[str] = []
    active_without_validation: list[str] = []
    test_nodes = _test_node_ids(inventory)

    for requirement in catalog.requirements:
        if not REQ_ID_RE.fullmatch(requirement.id):
            invalid_definitions.append(f"{requirement.id or '(missing id)'}: invalid stable ID")
        if requirement.revision < 1:
            invalid_definitions.append(f"{requirement.id}: revision must be >= 1")
        if " shall " not in f" {requirement.statement.lower()} ":
            invalid_definitions.append(f"{requirement.id}: normative statement must contain 'shall'")
        if not requirement.rationale:
            invalid_definitions.append(f"{requirement.id}: rationale is required")
        if not requirement.owner:
            invalid_definitions.append(f"{requirement.id}: owner is required")
        if requirement.status not in VALID_REQUIREMENT_STATUSES:
            invalid_definitions.append(f"{requirement.id}: invalid status {requirement.status!r}")
        if requirement.status == "active" and not requirement.implementation:
            invalid_definitions.append(f"{requirement.id}: active requirement needs implementation paths")
        if requirement.status == "active" and not requirement.validation_evidence:
            active_without_validation.append(requirement.id)
        for reference in requirement.implementation:
            if not _reference_exists(root, reference, test_nodes):
                missing_implementation.append(f"{requirement.id} -> {reference}")
        for field_name in EVIDENCE_FIELDS:
            for reference in getattr(requirement, field_name):
                if not _reference_exists(root, reference, test_nodes):
                    unresolved_evidence.append(f"{requirement.id} -> {reference}")

    alias_counts = Counter(alias for requirement in catalog.requirements for alias in requirement.aliases)
    duplicate_aliases = sorted(alias for alias, count in alias_counts.items() if count > 1)
    legacy_alias_errors: list[str] = []
    legacy_keys = Counter((alias.source, alias.legacy_id) for alias in catalog.legacy_aliases)
    for (source, legacy_id), count in legacy_keys.items():
        if count > 1:
            legacy_alias_errors.append(f"duplicate legacy alias {source}:{legacy_id}")
    for alias in catalog.legacy_aliases:
        if not alias.source or not alias.legacy_id or not alias.reason:
            legacy_alias_errors.append(f"incomplete legacy alias {alias.source}:{alias.legacy_id}")
        if alias.disposition not in {"alias", "superseded", "split"}:
            legacy_alias_errors.append(f"invalid legacy alias disposition {alias.source}:{alias.legacy_id}")
        missing_targets = sorted(set(alias.canonical_ids) - requirement_ids)
        if not alias.canonical_ids or missing_targets:
            legacy_alias_errors.append(
                f"legacy alias {alias.source}:{alias.legacy_id} missing canonical targets: "
                + (", ".join(missing_targets) or "none declared")
            )

    previous_by_id = {
        requirement.id: requirement
        for requirement in (previous_catalog.requirements if previous_catalog else [])
    }
    normative_revision_errors: list[str] = []
    for requirement in catalog.requirements:
        previous = previous_by_id.get(requirement.id)
        if previous is None:
            continue
        statement_changed = requirement.statement != previous.statement
        if statement_changed and requirement.revision <= previous.revision:
            normative_revision_errors.append(requirement.id)
        elif not statement_changed and requirement.revision < previous.revision:
            normative_revision_errors.append(requirement.id)
    removed_ids = sorted(set(previous_by_id) - requirement_ids)

    load_errors = list(catalog_load_errors or [])
    error_groups = (
        duplicates,
        invalid_definitions,
        duplicate_aliases,
        legacy_alias_errors,
        missing_implementation,
        unresolved_evidence,
        active_without_validation,
        normative_revision_errors,
        removed_ids,
        load_errors,
    )
    return TraceabilityReport(
        ok=not any(error_groups),
        catalog_requirements=sorted(requirement_ids),
        active_requirements=sorted(r.id for r in catalog.requirements if r.status == "active"),
        planned_requirements=sorted(r.id for r in catalog.requirements if r.status == "planned"),
        duplicate_requirement_ids=duplicates,
        invalid_requirement_definitions=sorted(set(invalid_definitions)),
        duplicate_aliases=duplicate_aliases,
        legacy_alias_errors=sorted(set(legacy_alias_errors)),
        missing_implementation_paths=sorted(set(missing_implementation)),
        unresolved_evidence_references=sorted(set(unresolved_evidence)),
        active_requirements_without_validation=sorted(set(active_without_validation)),
        normative_revision_errors=sorted(set(normative_revision_errors)),
        removed_requirement_ids=removed_ids,
        catalog_load_errors=load_errors,
        inventory_files=inventory.file_count,
        inventory_cases=inventory.total_cases,
    )


def build_inventory(root: Path) -> Inventory:
    entries: list[FileEntry] = []
    for path in sorted((root / "daemon/tests").rglob("test_*.py")):
        entries.append(_parse_python_test(path, root))
    for path in sorted((root / "extension/tests").rglob("*.test.js")):
        entries.append(_parse_node_test(path, root))
    python_cases = sum(len(entry.cases) for entry in entries if entry.platform == "pytest")
    node_cases = sum(len(entry.cases) for entry in entries if entry.platform == "node:test")
    catalog, catalog_load_errors = _load_catalog(root)
    inventory = Inventory(
        file_count=len(entries),
        total_cases=python_cases + node_cases,
        python_cases=python_cases,
        node_cases=node_cases,
        total_classes=sum(entry.classes for entry in entries),
        per_file=entries,
        catalog=catalog,
    )
    inventory.traceability = validate_catalog(
        root,
        catalog,
        inventory,
        previous_catalog=_load_head_catalog(root),
        catalog_load_errors=catalog_load_errors,
    )
    return inventory


def render_summary(inv: Inventory) -> str:
    return (
        f"> **Current inventory:** {inv.total_cases} static test functions across "
        f"{inv.file_count} files — {inv.python_cases} daemon pytest tests + "
        f"{inv.node_cases} extension node:test tests."
    )


def render_run(inv: Inventory) -> str:
    return (
        f"Latest inventory: **{inv.total_cases} static test functions** across "
        f"**{inv.file_count} files** ({inv.python_cases} daemon pytest; "
        f"{inv.node_cases} extension node:test). Regenerate with "
        f"`python3.11 scripts/generate_test_inventory.py --write`; enforce with "
        f"`--check`. Counts are source-level test functions, not pytest parametrized "
        f"case expansions."
    )


def _inline_refs(references: list[str]) -> str:
    return "<br>".join(f"`{_escape_cell(reference)}`" for reference in references) or "—"


def _inline_items(items: list[str]) -> str:
    return ", ".join(f"`{_escape_cell(item)}`" for item in items) or "—"


def render_traceability(inv: Inventory) -> str:
    trace = inv.traceability
    if trace is None:
        return "Traceability report unavailable."
    status = "✅ pass" if trace.ok else "❌ fail"

    def display(values: list[str]) -> str:
        return ", ".join(f"`{_escape_cell(value)}`" for value in values) or "none"

    return "\n".join(
        [
            f"Traceability gate: **{status}**.",
            "",
            "| Check | Result |",
            "|---|---|",
            f"| Catalog requirements | {len(trace.catalog_requirements)} ({len(trace.active_requirements)} active; {len(trace.planned_requirements)} planned) |",
            f"| Duplicate stable IDs | {display(trace.duplicate_requirement_ids)} |",
            f"| Invalid requirement definitions | {display(trace.invalid_requirement_definitions)} |",
            f"| Duplicate plan/local aliases | {display(trace.duplicate_aliases)} |",
            f"| Legacy alias errors | {display(trace.legacy_alias_errors)} |",
            f"| Missing implementation paths | {display(trace.missing_implementation_paths)} |",
            f"| Unresolved evidence/test nodes | {display(trace.unresolved_evidence_references)} |",
            f"| Active requirements without validation evidence | {display(trace.active_requirements_without_validation)} |",
            f"| Normative changes without revision increment | {display(trace.normative_revision_errors)} |",
            f"| Requirements removed without catalog disposition | {display(trace.removed_requirement_ids)} |",
            f"| Catalog load errors | {display(trace.catalog_load_errors)} |",
            f"| Static test inventory measured | {trace.inventory_cases} tests / {trace.inventory_files} files |",
        ]
    )


def render_requirements_trace(inv: Inventory) -> str:
    catalog = inv.catalog or RequirementCatalog(0, 0, [])
    requirements = sorted(catalog.requirements, key=lambda item: item.id)
    rows = [
        "| ID | Rev | Status | Normative requirement | Owner | Aliases | Implementation | Validation |",
        "|---|---:|---|---|---|---|---|---|",
    ]
    for requirement in requirements:
        rows.append(
            f"| {requirement.id} | {requirement.revision} | {requirement.status} | "
            f"{_escape_cell(requirement.statement)} | {_escape_cell(requirement.owner)} | "
            f"{_inline_items(requirement.aliases)} | {_inline_refs(requirement.implementation)} | "
            f"{_inline_refs(requirement.validation_evidence)} |"
        )
    if catalog.legacy_aliases:
        rows.extend(
            [
                "",
                "### Legacy alias reconciliation",
                "",
                "| Source | Legacy ID | Disposition | Canonical ID(s) | Reason |",
                "|---|---|---|---|---|",
            ]
        )
        for alias in catalog.legacy_aliases:
            rows.append(
                f"| {_escape_cell(alias.source)} | `{_escape_cell(alias.legacy_id)}` | "
                f"{_escape_cell(alias.disposition)} | {_inline_items(alias.canonical_ids)} | "
                f"{_escape_cell(alias.reason)} |"
            )
    return "\n".join(rows)


def render_requirement_coverage(inv: Inventory) -> str:
    requirements = sorted((inv.catalog.requirements if inv.catalog else []), key=lambda item: item.id)
    rows = [
        "| Requirement | Unit evidence | Integration evidence | System evidence | Operational evidence | Validation evidence |",
        "|---|---|---|---|---|---|",
    ]
    for requirement in requirements:
        rows.append(
            f"| {requirement.id} — {_escape_cell(requirement.statement)} | "
            f"{_inline_refs(requirement.unit_evidence)} | {_inline_refs(requirement.integration_evidence)} | "
            f"{_inline_refs(requirement.system_evidence)} | {_inline_refs(requirement.operational_evidence)} | "
            f"{_inline_refs(requirement.validation_evidence)} |"
        )
    return "\n".join(rows)


def render_requirement_posture(inv: Inventory) -> str:
    trace = inv.traceability
    if trace is None:
        return "Requirement catalog unavailable."
    return (
        f"The canonical catalog contains **{len(trace.catalog_requirements)} stable requirements**: "
        f"**{len(trace.active_requirements)} active** and **{len(trace.planned_requirements)} planned**. "
        f"Normative statements, implementation links, V-model evidence, and legacy aliases are owned by "
        f"[`requirements/catalog.toml`](../requirements/catalog.toml); generated tables in this doc set must not be hand-edited."
    )


def render_verification_depth(inv: Inventory) -> str:
    trace = inv.traceability
    active = len(trace.active_requirements) if trace else 0
    planned = len(trace.planned_requirements) if trace else 0
    return "\n".join(
        [
            f"- **Verification depth:** {inv.total_cases} static test functions across {inv.file_count} files "
            f"({inv.python_cases} daemon pytest; {inv.node_cases} extension node:test), plus real Chrome for Testing e2e.",
            f"- **Requirement authority:** `requirements/catalog.toml` defines {active} active and {planned} planned stable requirements with generated traceability tables.",
        ]
    )


def render_per_file(inv: Inventory) -> str:
    rows = [
        f"| `{entry.file}` | {entry.platform} | {len(entry.cases)} |"
        for entry in inv.per_file
    ]
    return "\n".join(
        [
            "| Test file | Runner | Test functions |",
            "|---|---|---:|",
            *rows,
            f"| **Total** |  | **{inv.total_cases}** |",
        ]
    )


def render_inventory(inv: Inventory) -> str:
    rows: list[str] = []
    for entry in inv.per_file:
        for case in entry.cases:
            rows.append(
                f"| `{entry.file}` | {entry.platform} | `{_escape_cell(case.suite)}` | "
                f"`{_escape_cell(case.name)}` | {case.line} | {_escape_cell(case.note)} |"
            )
    return "\n".join(
        [
            "| File | Runner | Suite | Test function | Line | Coverage note |",
            "|---|---|---|---|---:|---|",
            *rows,
        ]
    )


TEST_DOC_RENDERERS = {
    "inventory-summary": render_summary,
    "audit-run": render_run,
    "traceability-gate": render_traceability,
    "per-file-counts": render_per_file,
    "test-case-inventory": render_inventory,
}

REPOSITORY_DOC_RENDERERS = {
    TARGET_DOC: TEST_DOC_RENDERERS,
    Path("docs/ARCHITECTURE.md"): {"requirements-trace": render_requirements_trace},
    Path("docs/test-plan.md"): {"requirement-coverage": render_requirement_coverage},
    Path("docs/STATUS.md"): {"requirement-posture": render_requirement_posture},
    Path("docs/EXECUTIVE_BRIEF.md"): {"verification-depth": render_verification_depth},
}


def replace_region(doc: str, region_id: str, body: str, *, target: Path = TARGET_DOC) -> str:
    begin = f"<!-- BEGIN GENERATED:{region_id} -->"
    end = f"<!-- END GENERATED:{region_id} -->"
    start = doc.find(begin)
    stop = doc.find(end)
    if start == -1 or stop == -1 or stop < start:
        raise ValueError(f"missing GENERATED markers for {region_id!r} in {target}")
    return doc[: start + len(begin)] + "\n" + body + "\n" + doc[stop:]


def _render_regions(
    doc: str,
    inv: Inventory,
    renderers: dict[str, Callable[[Inventory], str]],
    *,
    target: Path,
) -> str:
    for region_id, renderer in renderers.items():
        doc = replace_region(doc, region_id, renderer(inv), target=target)
    return doc.rstrip("\n") + "\n"


def render_doc(doc: str, inv: Inventory) -> str:
    return _render_regions(doc, inv, TEST_DOC_RENDERERS, target=TARGET_DOC)


def render_repository_docs(root: Path, inv: Inventory) -> dict[Path, str]:
    rendered: dict[Path, str] = {}
    for relative_path, renderers in REPOSITORY_DOC_RENDERERS.items():
        path = root / relative_path
        if not path.exists():
            raise FileNotFoundError(f"missing generated-document target: {relative_path}")
        rendered[path] = _render_regions(
            path.read_text(encoding="utf-8"),
            inv,
            renderers,
            target=relative_path,
        )
    return rendered


def _print_traceability_errors(trace: TraceabilityReport) -> None:
    groups = [
        ("catalog load errors", trace.catalog_load_errors),
        ("duplicate requirement IDs", trace.duplicate_requirement_ids),
        ("invalid requirement definitions", trace.invalid_requirement_definitions),
        ("duplicate aliases", trace.duplicate_aliases),
        ("legacy alias errors", trace.legacy_alias_errors),
        ("missing implementation paths", trace.missing_implementation_paths),
        ("unresolved evidence/test references", trace.unresolved_evidence_references),
        ("active requirements without validation evidence", trace.active_requirements_without_validation),
        ("normative changes without revision increment", trace.normative_revision_errors),
        ("requirements removed without catalog disposition", trace.removed_requirement_ids),
    ]
    for label, values in groups:
        if values:
            sys.stderr.write(f"ERROR {label}: " + ", ".join(values) + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate test inventory and requirement traceability docs.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_const", const="write", dest="mode")
    mode.add_argument("--check", action="store_const", const="check", dest="mode")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", default=None)
    parser.set_defaults(mode="check")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.root or os.getcwd()).resolve()
    inv = build_inventory(root)
    if args.json:
        print(json.dumps(asdict(inv), indent=2))
        return 0 if inv.traceability and inv.traceability.ok else 1

    rendered = render_repository_docs(root, inv)
    changed = [path for path, updated in rendered.items() if path.read_text(encoding="utf-8") != updated]
    if args.mode == "write":
        if inv.traceability and not inv.traceability.ok:
            _print_traceability_errors(inv.traceability)
            return 1
        for path in changed:
            path.write_text(rendered[path], encoding="utf-8")
        action = "updated" if changed else "already current"
        paths = ", ".join(path.relative_to(root).as_posix() for path in changed) or "generated docs"
        print(
            f"{action} {paths}: {inv.total_cases} tests / {inv.file_count} files "
            f"({inv.python_cases} pytest, {inv.node_cases} node:test)"
        )
        return 0

    if changed:
        stale = ", ".join(path.relative_to(root).as_posix() for path in changed)
        sys.stderr.write(
            f"ERROR generated docs are stale: {stale}. Run: python3.11 scripts/generate_test_inventory.py --write\n"
        )
        return 1
    if inv.traceability and not inv.traceability.ok:
        _print_traceability_errors(inv.traceability)
        return 1
    print(
        f"generated docs ok: {inv.total_cases} tests / {inv.file_count} files "
        f"({inv.python_cases} pytest, {inv.node_cases} node:test); "
        f"{len(inv.traceability.catalog_requirements) if inv.traceability else 0} requirements"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
