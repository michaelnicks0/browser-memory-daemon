#!/usr/bin/env python3
"""Generate docs/TESTS.md inventory from daemon pytest and extension node:test sources.

The inventory is static and body-safe: it parses test names, source paths, and line
numbers without executing browser captures or reading runtime data. It counts Python
``test_*`` functions/methods and top-level JavaScript ``test(...)`` registrations.
"""
from __future__ import annotations

import argparse
import ast
import html
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

TARGET_DOC = Path("docs/TESTS.md")
REGION_IDS = ("inventory-summary", "audit-run", "traceability-gate", "per-file-counts", "test-case-inventory")
REQ_ID_RE = re.compile(r"\bREQ-\d+[A-Z]?\b")


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
    architecture_requirements: list[str]
    test_plan_requirements: list[str]
    missing_test_plan_requirements: list[str]
    unresolved_reference_paths: list[str]
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


def _requirement_ids_from_markdown(path: Path) -> list[str]:
    if not path.exists():
        return []
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("|"):
            ids.update(REQ_ID_RE.findall(line))
    return sorted(ids)


def _reference_candidates(path: Path) -> list[str]:
    if not path.exists():
        return []
    refs: list[str] = []
    for match in re.finditer(r"`([^`]+)`", path.read_text(encoding="utf-8")):
        ref = match.group(1).split("::", 1)[0].strip().strip(".,;:")
        if not ref or " " in ref or ref.startswith(("/", "#", "http://", "https://")):
            continue
        if ref.startswith(("daemon/", "extension/", "scripts/", "docs/", "ui/")):
            refs.append(ref)
        elif ref in {"pyproject.toml", "requirements-dev.txt", "extension/package.json", ".gitignore"}:
            refs.append(ref)
        elif "/" not in ref and ref.endswith((".py", ".js", ".mjs", ".sh", ".md", ".json", ".toml")):
            refs.append(ref)
    return sorted(set(refs))


def _reference_exists(root: Path, ref: str) -> bool:
    candidate = root / ref
    if candidate.exists():
        return True
    if "/" in ref:
        return False
    skip_dirs = {".git", ".venv", "node_modules", "dist", "__pycache__"}
    for path in root.rglob(ref):
        if skip_dirs & set(path.parts):
            continue
        if path.exists():
            return True
    return False


def build_traceability(root: Path, inventory: Inventory) -> TraceabilityReport:
    architecture_requirements = _requirement_ids_from_markdown(root / "docs/ARCHITECTURE.md")
    test_plan_requirements = _requirement_ids_from_markdown(root / "docs/test-plan.md")
    missing = sorted(set(architecture_requirements) - set(test_plan_requirements))
    unresolved_refs = [
        ref
        for ref in _reference_candidates(root / "docs/test-plan.md")
        if not _reference_exists(root, ref)
    ]
    return TraceabilityReport(
        ok=not missing and not unresolved_refs,
        architecture_requirements=architecture_requirements,
        test_plan_requirements=test_plan_requirements,
        missing_test_plan_requirements=missing,
        unresolved_reference_paths=unresolved_refs,
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
    inventory = Inventory(
        file_count=len(entries),
        total_cases=python_cases + node_cases,
        python_cases=python_cases,
        node_cases=node_cases,
        total_classes=sum(entry.classes for entry in entries),
        per_file=entries,
    )
    inventory.traceability = build_traceability(root, inventory)
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


def render_traceability(inv: Inventory) -> str:
    trace = inv.traceability
    if trace is None:
        return "Traceability report unavailable."
    status = "✅ pass" if trace.ok else "❌ fail"
    missing = ", ".join(f"`{req}`" for req in trace.missing_test_plan_requirements) or "none"
    unresolved = ", ".join(f"`{ref}`" for ref in trace.unresolved_reference_paths) or "none"
    return "\n".join(
        [
            f"Traceability gate: **{status}**.",
            "",
            "| Check | Result |",
            "|---|---|",
            f"| Architecture requirements found | {len(trace.architecture_requirements)} |",
            f"| Test-plan requirement rows found | {len(trace.test_plan_requirements)} |",
            f"| Missing architecture requirements in `docs/test-plan.md` | {missing} |",
            f"| Unresolved file/test references in `docs/test-plan.md` | {unresolved} |",
            f"| Static test inventory measured | {trace.inventory_cases} tests / {trace.inventory_files} files |",
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


RENDERERS = {
    "inventory-summary": render_summary,
    "audit-run": render_run,
    "traceability-gate": render_traceability,
    "per-file-counts": render_per_file,
    "test-case-inventory": render_inventory,
}


def replace_region(doc: str, region_id: str, body: str) -> str:
    begin = f"<!-- BEGIN GENERATED:{region_id} -->"
    end = f"<!-- END GENERATED:{region_id} -->"
    start = doc.find(begin)
    stop = doc.find(end)
    if start == -1 or stop == -1 or stop < start:
        raise ValueError(f"missing GENERATED markers for {region_id!r} in {TARGET_DOC}")
    return doc[: start + len(begin)] + "\n" + body + "\n" + doc[stop:]


def render_doc(doc: str, inv: Inventory) -> str:
    for region_id, renderer in RENDERERS.items():
        doc = replace_region(doc, region_id, renderer(inv))
    return doc.rstrip("\n") + "\n"


def _print_traceability_errors(trace: TraceabilityReport) -> None:
    if trace.missing_test_plan_requirements:
        sys.stderr.write(
            "ERROR docs/test-plan.md missing architecture requirement rows: "
            + ", ".join(trace.missing_test_plan_requirements)
            + "\n"
        )
    if trace.unresolved_reference_paths:
        sys.stderr.write(
            "ERROR docs/test-plan.md has unresolved file/test references: "
            + ", ".join(trace.unresolved_reference_paths)
            + "\n"
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate docs/TESTS.md inventory.")
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
        return 0

    doc_path = root / TARGET_DOC
    original = doc_path.read_text(encoding="utf-8")
    updated = render_doc(original, inv)
    if args.mode == "write":
        if updated != original:
            doc_path.write_text(updated, encoding="utf-8")
            print(
                f"updated {TARGET_DOC}: {inv.total_cases} tests / {inv.file_count} files "
                f"({inv.python_cases} pytest, {inv.node_cases} node:test)"
            )
        else:
            print(f"{TARGET_DOC} already current ({inv.total_cases} tests)")
        if inv.traceability and not inv.traceability.ok:
            _print_traceability_errors(inv.traceability)
            return 1
        return 0
    if updated != original:
        sys.stderr.write(
            f"ERROR {TARGET_DOC} is stale. Run: python3.11 scripts/generate_test_inventory.py --write\n"
        )
        return 1
    if inv.traceability and not inv.traceability.ok:
        _print_traceability_errors(inv.traceability)
        return 1
    print(
        f"{TARGET_DOC} ok: {inv.total_cases} tests / {inv.file_count} files "
        f"({inv.python_cases} pytest, {inv.node_cases} node:test)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
