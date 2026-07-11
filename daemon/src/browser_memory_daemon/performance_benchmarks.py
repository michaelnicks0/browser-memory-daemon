from __future__ import annotations

import argparse
import base64
import json
import math
import shutil
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .config import RuntimeConfig
from .db import audit, connect, init_db
from .ingest import ingest_capture
from .media import claim_media_fetch_tasks, media_queue_status
from .media_worker import run_once as run_media_worker_once
from .models import CapturePayload
from .ops import doctor, document_detail, recent_captures, snapshot_detail, timeline
from .search import search_memory


@dataclass(frozen=True)
class BenchmarkOptions:
    captures: int = 100
    read_repetitions: int = 5
    paragraphs_per_capture: int = 3
    media_every: int = 2
    media_worker_limit: int = 100
    domain_count: int = 8
    seed: str = "bmd-synthetic-v1"
    runtime_root: Path | None = None
    keep_runtime_root: bool = False


SMALL_OPTIONS = {
    "captures": 40,
    "read_repetitions": 5,
    "paragraphs_per_capture": 3,
    "media_every": 2,
    "media_worker_limit": 50,
}

ADVISORY_BUDGETS_MS = {
    "ingest_mean_ms": 75.0,
    "search_with_audit_p95_ms": 150.0,
    "recent_with_audit_p95_ms": 150.0,
    "timeline_with_audit_p95_ms": 200.0,
    "document_detail_with_audit_p95_ms": 250.0,
    "snapshot_detail_with_audit_p95_ms": 250.0,
    "media_queue_status_with_audit_p95_ms": 150.0,
    "media_worker_task_selection_ms": 150.0,
    "media_worker_run_once_ms": 2_000.0,
}


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = max(0, min(len(sorted_values) - 1, math.ceil(len(sorted_values) * fraction) - 1))
    return sorted_values[index]


def _round_ms(value: float) -> float:
    return round(value, 3)


def _duration_stats(samples_ms: list[float]) -> dict[str, Any]:
    ordered = sorted(samples_ms)
    return {
        "samples": len(samples_ms),
        "min_ms": _round_ms(ordered[0] if ordered else 0.0),
        "mean_ms": _round_ms(statistics.fmean(samples_ms) if samples_ms else 0.0),
        "p50_ms": _round_ms(_percentile(ordered, 0.50)),
        "p95_ms": _round_ms(_percentile(ordered, 0.95)),
        "max_ms": _round_ms(ordered[-1] if ordered else 0.0),
    }


def _measure_samples(
    label: str,
    repetitions: int,
    fn: Callable[[], Any],
    *,
    count_fn: Callable[[Any], int] | None = None,
) -> dict[str, Any]:
    samples_ms: list[float] = []
    counts: list[int] = []
    last_result: Any = None
    for _ in range(max(1, repetitions)):
        started = time.perf_counter_ns()
        last_result = fn()
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        samples_ms.append(elapsed_ms)
        if count_fn:
            counts.append(int(count_fn(last_result)))
    metric = {"label": label, **_duration_stats(samples_ms)}
    if counts:
        metric["result_count"] = counts[-1]
        metric["result_count_min"] = min(counts)
        metric["result_count_max"] = max(counts)
    return metric


def _measure_once(label: str, fn: Callable[[], Any], *, count_fn: Callable[[Any], int] | None = None) -> tuple[dict[str, Any], Any]:
    result: Any = None

    def run() -> Any:
        nonlocal result
        result = fn()
        return result

    metric = _measure_samples(label, 1, run, count_fn=count_fn)
    return metric, result


def _resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _benchmark_paths(config: RuntimeConfig) -> dict[str, Path]:
    return {
        "config_root": config.config_root,
        "data_root": config.data_root,
        "state_root": config.state_root,
        "blob_root": config.blob_root,
        "db_path": config.db_path,
        "clean_text_root": config.clean_text_root,
        "raw_html_root": config.raw_html_root,
        "media_root": config.media_root,
        "audit_log_path": config.audit_log_path,
    }


def _assert_benchmark_paths_contained(config: RuntimeConfig, runtime_root: Path) -> dict[str, str]:
    resolved_root = _resolve_path(runtime_root)
    violations: dict[str, str] = {}
    resolved_paths: dict[str, str] = {}
    for name, path in _benchmark_paths(config).items():
        resolved = _resolve_path(path)
        resolved_paths[name] = str(resolved)
        if not resolved.is_relative_to(resolved_root):
            violations[name] = str(resolved)
    if violations:
        formatted = ", ".join(f"{name}={path}" for name, path in sorted(violations.items()))
        raise RuntimeError(f"benchmark path containment failed for runtime {resolved_root}: {formatted}")
    return {"runtime_root": str(resolved_root), **resolved_paths}


def _benchmark_config(runtime_root: Path) -> RuntimeConfig:
    cfg = RuntimeConfig(
        api_token="benchmark-token",
        policy_mode="all",
        config_root=runtime_root / "config",
        data_root=runtime_root / "data",
        blob_root=runtime_root / "blobs",
        state_root=runtime_root / "state",
        media_fetch_timeout_seconds=1.0,
    )
    _assert_benchmark_paths_contained(cfg, runtime_root)
    cfg.ensure_dirs()
    return cfg


def _iso_at(index: int) -> str:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return (base + timedelta(seconds=index * 17)).isoformat().replace("+00:00", "Z")


def _media_ref(index: int) -> dict[str, Any]:
    payload = base64.b64encode(f"synthetic-media-{index}".encode("utf-8")).decode("ascii")
    return {
        "media_type": "image",
        "role": "content",
        "source_url": f"data:image/png;base64,{payload}",
        "mime_type": "image/png",
        "width": 640 + (index % 5),
        "height": 360 + (index % 3),
        "alt_text": f"Synthetic benchmark image {index}",
        "metadata": {"priority": 60 + (index % 10), "synthetic": True},
    }


def _payload(index: int, options: BenchmarkOptions) -> CapturePayload:
    domain_index = index % options.domain_count
    query_index = index % 10
    url = f"http://synthetic-{domain_index}.example.test/articles/{index:05d}"
    paragraphs = []
    for paragraph_index in range(options.paragraphs_per_capture):
        paragraphs.append(
            " ".join(
                [
                    f"Synthetic browser memory benchmark document {index:05d} paragraph {paragraph_index}.",
                    "benchmarkalpha sharedterm durableperformancecoverage.",
                    f"domainmarker{domain_index} querymarker{query_index} seed {options.seed}.",
                    "This deterministic fixture text is generated locally and contains no captured live browsing data.",
                    f"Sequence token {index:05d}-{paragraph_index} repeats benchmarkalpha for FTS coverage.",
                ]
            )
        )
    media_artifacts = []
    if options.media_every > 0 and index % options.media_every == 0:
        media_artifacts.append(_media_ref(index))
    captured_at = _iso_at(index)
    return CapturePayload(
        url=url,
        canonical_url=url,
        title=f"Synthetic Benchmark Article {index:05d}",
        text="\n\n".join(paragraphs),
        visit_id=f"benchmark-visit-{index:05d}",
        captured_at=captured_at,
        visit_started_at=captured_at,
        dwell_seconds=30 + (index % 90),
        browser_profile="BenchmarkProfile",
        source_device="synthetic-benchmark",
        media_artifacts=media_artifacts,
    )


def _ingest_dataset(conn, config: RuntimeConfig, options: BenchmarkOptions) -> dict[str, Any]:
    samples_ms: list[float] = []
    stored: list[dict[str, Any]] = []
    chunk_count = 0
    media_ref_count = 0
    for index in range(options.captures):
        payload = _payload(index, options)
        started = time.perf_counter_ns()
        result = ingest_capture(conn, config, payload)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        samples_ms.append(elapsed_ms)
        stored.append(result)
        chunk_count += int(result.get("chunk_count") or 0)
        media_ref_count += int(result.get("media_ref_count") or 0)
    return {
        **_duration_stats(samples_ms),
        "captures": len(stored),
        "chunks": chunk_count,
        "media_refs": media_ref_count,
        "first_document_id": stored[0]["document_id"] if stored else "",
        "first_snapshot_id": stored[0]["snapshot_id"] if stored else "",
        "last_document_id": stored[-1]["document_id"] if stored else "",
        "last_snapshot_id": stored[-1]["snapshot_id"] if stored else "",
    }


def _with_audit(conn, event_type: str, fn: Callable[[], Any], metadata_fn: Callable[[Any], dict[str, Any]]) -> Any:
    result = fn()
    audit(conn, event_type, metadata_fn(result))
    conn.commit()
    return result


def _read_surface_metrics(conn, config: RuntimeConfig, options: BenchmarkOptions, ingest: dict[str, Any]) -> dict[str, Any]:
    first_document_id = str(ingest["first_document_id"])
    first_snapshot_id = str(ingest["first_snapshot_id"])
    query = "benchmarkalpha querymarker1"
    surfaces: dict[str, dict[str, Any]] = {}

    definitions: list[tuple[str, str, Callable[[], Any], Callable[[Any], int], Callable[[Any], dict[str, Any]]]] = [
        (
            "search",
            "search",
            lambda: search_memory(conn, query, limit=20),
            lambda result: len(result),
            lambda result: {"query_len": len(query), "result_count": len(result)},
        ),
        (
            "recent",
            "recent",
            lambda: recent_captures(conn, limit=25),
            lambda result: len(result),
            lambda result: {"result_count": len(result)},
        ),
        (
            "timeline",
            "timeline",
            lambda: timeline(conn, day="2026-01-01", limit=100),
            lambda result: int(result.get("count") or 0),
            lambda result: {"result_count": int(result.get("count") or 0)},
        ),
        (
            "document_detail",
            "document.detail",
            lambda: document_detail(conn, config, first_document_id),
            lambda result: len(result.get("visits") or []) + len(result.get("snapshots") or []) + len(result.get("chunks") or []),
            lambda _result: {"document_id": first_document_id},
        ),
        (
            "snapshot_detail",
            "snapshot.detail",
            lambda: snapshot_detail(conn, config, first_snapshot_id),
            lambda result: len(result.get("chunks") or []) + len(result.get("text") or ""),
            lambda _result: {"snapshot_id": first_snapshot_id},
        ),
        (
            "media_queue_status",
            "media.queue_status",
            lambda: media_queue_status(conn, config, limit=50),
            lambda result: sum(int(value) for value in result.get("artifacts", {}).values()),
            lambda _result: {},
        ),
        (
            "doctor",
            "doctor",
            lambda: doctor(config, conn),
            lambda result: sum(int(value) for value in result.get("database", {}).get("counts", {}).values()),
            lambda result: {"ok": bool(result.get("ok"))},
        ),
    ]

    for label, event_type, fn, count_fn, metadata_fn in definitions:
        direct = _measure_samples(f"{label}.direct", options.read_repetitions, fn, count_fn=count_fn)
        with_audit = _measure_samples(
            f"{label}.with_audit",
            options.read_repetitions,
            lambda fn=fn, event_type=event_type, metadata_fn=metadata_fn: _with_audit(conn, event_type, fn, metadata_fn),
            count_fn=count_fn,
        )
        surfaces[label] = {
            "direct": direct,
            "with_audit": with_audit,
            "audit_write_overhead_mean_ms_estimate": _round_ms(with_audit["mean_ms"] - direct["mean_ms"]),
        }
    return surfaces


def _measure_task_selection(conn, limit: int) -> tuple[dict[str, Any], list[Any]]:
    def select_rows() -> list[Any]:
        if conn.in_transaction:
            conn.rollback()
        conn.execute("BEGIN")
        try:
            rows = claim_media_fetch_tasks(
                conn,
                worker_id="benchmark-selection-probe",
                worker_kind="daemon-public",
                limit=limit,
            )
            return list(rows)
        finally:
            conn.rollback()

    return _measure_once("media_worker.task_selection", select_rows, count_fn=len)


def _table_counts(conn) -> dict[str, int]:
    tables = [
        "documents",
        "visits",
        "snapshots",
        "chunks",
        "chunks_fts",
        "media_artifacts",
        "media_fetch_tasks",
        "audit_events",
    ]
    return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def _sum_files(root: Path) -> tuple[int, int]:
    if not root.exists():
        return 0, 0
    count = 0
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            count += 1
            total += path.stat().st_size
    return count, total


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _storage_summary(config: RuntimeConfig, conn) -> dict[str, Any]:
    clean_files, clean_bytes = _sum_files(config.clean_text_root)
    media_files, media_bytes = _sum_files(config.media_root)
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    db_path = config.db_path
    wal_path = Path(f"{db_path}-wal")
    shm_path = Path(f"{db_path}-shm")
    return {
        "db_path": str(db_path),
        "db_bytes": _file_size(db_path),
        "wal_bytes": _file_size(wal_path),
        "shm_bytes": _file_size(shm_path),
        "sqlite_page_count": page_count,
        "sqlite_page_size": page_size,
        "sqlite_logical_bytes": page_count * page_size,
        "clean_text_files": clean_files,
        "clean_text_bytes": clean_bytes,
        "media_files": media_files,
        "media_bytes": media_bytes,
        "total_sidecar_bytes": clean_bytes + media_bytes,
    }


def _advisory_budget_checks(benchmarks: dict[str, Any]) -> dict[str, Any]:
    observed = {
        "ingest_mean_ms": benchmarks["ingest"]["mean_ms"],
        "search_with_audit_p95_ms": benchmarks["read_surfaces"]["search"]["with_audit"]["p95_ms"],
        "recent_with_audit_p95_ms": benchmarks["read_surfaces"]["recent"]["with_audit"]["p95_ms"],
        "timeline_with_audit_p95_ms": benchmarks["read_surfaces"]["timeline"]["with_audit"]["p95_ms"],
        "document_detail_with_audit_p95_ms": benchmarks["read_surfaces"]["document_detail"]["with_audit"]["p95_ms"],
        "snapshot_detail_with_audit_p95_ms": benchmarks["read_surfaces"]["snapshot_detail"]["with_audit"]["p95_ms"],
        "media_queue_status_with_audit_p95_ms": benchmarks["read_surfaces"]["media_queue_status"]["with_audit"]["p95_ms"],
        "media_worker_task_selection_ms": benchmarks["media_worker"]["task_selection"]["max_ms"],
        "media_worker_run_once_ms": benchmarks["media_worker"]["run_once"]["max_ms"],
    }
    checks = {}
    for name, budget_ms in ADVISORY_BUDGETS_MS.items():
        value = float(observed.get(name, 0.0))
        checks[name] = {"observed_ms": _round_ms(value), "budget_ms": budget_ms, "ok": value <= budget_ms}
    return {"advisory": True, "checks": checks, "failed": [name for name, item in checks.items() if not item["ok"]]}


def run_benchmark(options: BenchmarkOptions) -> dict[str, Any]:
    cleanup = False
    config: RuntimeConfig | None = None
    if options.runtime_root is None:
        runtime_root = Path(tempfile.mkdtemp(prefix="browser-memory-benchmark-"))
        (runtime_root / ".benchmark-runtime-root").write_text("browser-memory-daemon synthetic benchmark\n", encoding="utf-8")
        cleanup = not options.keep_runtime_root
    else:
        runtime_root = options.runtime_root.expanduser().resolve()
        runtime_root.mkdir(parents=True, exist_ok=True)
    try:
        config = _benchmark_config(runtime_root)
        containment = _assert_benchmark_paths_contained(config, runtime_root)
        init_db(config)
        with connect(config.db_path) as conn:
            ingest = _ingest_dataset(conn, config, options)
            read_surfaces = _read_surface_metrics(conn, config, options, ingest)
            task_selection, selected_rows = _measure_task_selection(conn, options.media_worker_limit)
            worker_metric, worker_summary = _measure_once(
                "media_worker.run_once",
                lambda: run_media_worker_once(
                    conn,
                    config,
                    worker_id="benchmark-worker",
                    worker_kind="daemon-public",
                    limit=options.media_worker_limit,
                ),
                count_fn=lambda result: int(result.get("attempted") or 0),
            )
            queue_after = media_queue_status(conn, config, limit=25)
            conn.commit()
            benchmarks = {
                "ingest": ingest,
                "read_surfaces": read_surfaces,
                "media_worker": {
                    "task_selection": {**task_selection, "selected_task_count": len(selected_rows)},
                    "run_once": worker_metric,
                    "run_once_summary": {k: v for k, v in worker_summary.items() if k != "results"},
                    "queue_after": queue_after,
                },
            }
            storage = _storage_summary(config, conn)
            counts = _table_counts(conn)
        result = {
            "ok": True,
            "suite": "browser-memory-daemon-performance-benchmarks",
            "profile": "synthetic-small" if options.captures <= SMALL_OPTIONS["captures"] else "synthetic",
            "dataset": {
                "seed": options.seed,
                "captures": options.captures,
                "domain_count": options.domain_count,
                "paragraphs_per_capture": options.paragraphs_per_capture,
                "media_every": options.media_every,
                "captured_text_source": "deterministic synthetic generator; no live captured text fixtures",
            },
            "runtime": {**containment, "runtime_root_retained": not cleanup},
            "counts": counts,
            "benchmarks": benchmarks,
            "storage": storage,
        }
        result["budgets"] = _advisory_budget_checks(benchmarks)
        return result
    finally:
        if cleanup:
            _cleanup_benchmark_runtime(runtime_root, config)


def _cleanup_benchmark_runtime(runtime_root: Path, config: RuntimeConfig | None) -> None:
    resolved_root = _resolve_path(runtime_root)
    if resolved_root.is_symlink() or not resolved_root.is_dir():
        raise RuntimeError(f"refusing to remove non-directory benchmark runtime root: {resolved_root}")
    if not resolved_root.name.startswith("browser-memory-benchmark-"):
        raise RuntimeError(f"refusing to remove unexpected benchmark runtime root: {resolved_root}")
    marker = resolved_root / ".benchmark-runtime-root"
    if not marker.is_file():
        raise RuntimeError(f"refusing to remove unmarked benchmark runtime root: {resolved_root}")
    if config is not None:
        _assert_benchmark_paths_contained(config, resolved_root)
    shutil.rmtree(resolved_root)


def human_summary(result: dict[str, Any]) -> str:
    ingest = result["benchmarks"]["ingest"]
    read = result["benchmarks"]["read_surfaces"]
    media_worker = result["benchmarks"]["media_worker"]
    storage = result["storage"]
    failed = result["budgets"].get("failed") or []
    lines = [
        "BMD performance benchmark summary",
        f"dataset: captures={result['dataset']['captures']} chunks={ingest['chunks']} media_refs={ingest['media_refs']} seed={result['dataset']['seed']}",
        f"ingest: mean={ingest['mean_ms']}ms p95={ingest['p95_ms']}ms max={ingest['max_ms']}ms",
        f"search+audit: p95={read['search']['with_audit']['p95_ms']}ms results={read['search']['with_audit'].get('result_count', 0)} overhead≈{read['search']['audit_write_overhead_mean_ms_estimate']}ms",
        f"recent+audit: p95={read['recent']['with_audit']['p95_ms']}ms results={read['recent']['with_audit'].get('result_count', 0)} overhead≈{read['recent']['audit_write_overhead_mean_ms_estimate']}ms",
        f"timeline+audit: p95={read['timeline']['with_audit']['p95_ms']}ms results={read['timeline']['with_audit'].get('result_count', 0)} overhead≈{read['timeline']['audit_write_overhead_mean_ms_estimate']}ms",
        f"detail+audit: document_p95={read['document_detail']['with_audit']['p95_ms']}ms snapshot_p95={read['snapshot_detail']['with_audit']['p95_ms']}ms",
        f"media worker: selection={media_worker['task_selection']['max_ms']}ms selected={media_worker['task_selection']['selected_task_count']} run_once={media_worker['run_once']['max_ms']}ms attempted={media_worker['run_once'].get('result_count', 0)}",
        f"storage: db={storage['db_bytes']}B wal={storage['wal_bytes']}B shm={storage['shm_bytes']}B clean_text={storage['clean_text_bytes']}B media={storage['media_bytes']}B",
        "budgets: advisory " + ("ok" if not failed else "exceeded " + ", ".join(failed)),
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic Browser Memory Daemon performance benchmarks.")
    parser.add_argument("--small", action="store_true", help="Use the standard small synthetic profile.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    parser.add_argument("--runtime-root", type=Path, help="Runtime root to use for benchmark data; defaults to a temporary WSL path.")
    parser.add_argument("--keep-runtime-root", action="store_true", help="Retain the temporary runtime root when --runtime-root is omitted.")
    parser.add_argument("--captures", type=int, help="Number of synthetic captures to ingest.")
    parser.add_argument("--read-repetitions", type=int, help="Read samples per surface.")
    parser.add_argument("--paragraphs-per-capture", type=int, help="Synthetic paragraphs per capture.")
    parser.add_argument("--media-every", type=int, help="Attach one data-URL media ref every N captures; 0 disables media refs.")
    parser.add_argument("--media-worker-limit", type=int, help="Maximum media tasks selected/processed by the worker benchmark.")
    parser.add_argument("--domain-count", type=int, default=8, help="Number of synthetic domains to distribute captures across.")
    parser.add_argument("--seed", default="bmd-synthetic-v1", help="Dataset seed label recorded in output.")
    return parser


def options_from_args(args: argparse.Namespace) -> BenchmarkOptions:
    defaults = SMALL_OPTIONS if args.small else {}

    def selected(name: str, fallback: int) -> int:
        value = getattr(args, name)
        if value is not None:
            return value
        return int(defaults.get(name, fallback))

    return BenchmarkOptions(
        captures=selected("captures", BenchmarkOptions.captures),
        read_repetitions=selected("read_repetitions", BenchmarkOptions.read_repetitions),
        paragraphs_per_capture=selected("paragraphs_per_capture", BenchmarkOptions.paragraphs_per_capture),
        media_every=selected("media_every", BenchmarkOptions.media_every),
        media_worker_limit=selected("media_worker_limit", BenchmarkOptions.media_worker_limit),
        domain_count=max(1, int(args.domain_count)),
        seed=str(args.seed),
        runtime_root=args.runtime_root,
        keep_runtime_root=bool(args.keep_runtime_root),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_benchmark(options_from_args(args))
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(human_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
