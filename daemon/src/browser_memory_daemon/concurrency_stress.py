from __future__ import annotations

import argparse
import base64
import json
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypeVar

from .app import make_server
from .config import RuntimeConfig, load_config
from .db import connect
from .media_worker import run_once as run_media_worker_once

TOKEN = "stress-token"
SHARED_NEEDLE = "BMD_CONCURRENCY_STRESS_SHARED_TOKEN"
T = TypeVar("T")


@dataclass(frozen=True)
class StressOptions:
    captures: int = 12
    reader_rounds: int = 12
    media_worker_runs: int = 4
    max_workers: int = 16
    timeout_seconds: float = 30.0
    token: str = TOKEN
    policy_mode: str = "all"
    runtime_root: Path | None = None
    keep_runtime: bool = False


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _json_request(method: str, url: str, *, token: str, body: dict[str, Any] | None = None, timeout: float = 10.0) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
        return response.status, json.loads(payload or "{}")


def _binary_request(
    method: str,
    url: str,
    *,
    token: str,
    body: bytes,
    content_type: str,
    headers: dict[str, str],
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", content_type)
    for key, value in headers.items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
        return response.status, json.loads(payload or "{}")


def _data_url(seed: str) -> str:
    content = f"stress-media-{seed}".encode()
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _capture_payload(index: int) -> dict[str, Any]:
    captured_at = f"2026-07-03T00:{index % 60:02d}:00Z"
    return {
        "visit_id": f"stress-visit-{index:04d}",
        "url": f"https://stress.example.test/doc-{index:04d}",
        "title": f"Stress Fixture {index:04d}",
        "text": f"{SHARED_NEEDLE} capture {index:04d} body for deterministic SQLite contention exercise.",
        "captured_at": captured_at,
        "media_artifacts": [
            {
                "media_type": "image",
                "source_url": _data_url(f"capture-{index}"),
                "mime_type": "image/png",
                "alt_text": f"stress image {index:04d}",
                "metadata": {"priority": 80},
            }
        ],
    }


def _event_payload(capture: dict[str, Any], index: int) -> dict[str, Any]:
    minute = index % 60
    fixture = _capture_payload(index)
    return {
        "event_id": f"stress-event-{index:04d}",
        "visit_id": capture.get("visit_id") or fixture["visit_id"],
        "url": capture.get("url") or fixture["url"],
        "event_type": "tab-deactivated",
        "event_started_at": f"2026-07-03T01:{minute:02d}:00Z",
        "event_ended_at": f"2026-07-03T01:{minute:02d}:05Z",
        "active_seconds": 5,
        "max_scroll_percent": 75,
        "metadata": {"stress_harness": True, "index": index},
    }


def _run_concurrent(
    name: str,
    items: Iterable[T],
    fn: Callable[[T], Any],
    *,
    max_workers: int,
    timeout_seconds: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    materialized = list(items)
    if not materialized:
        return {"name": name, "attempted": 0, "ok": 0, "failed": 0, "duration_ms": 0}, []
    worker_count = _clamp_int(max_workers, minimum=1, maximum=max(1, len(materialized)))
    barrier = threading.Barrier(worker_count) if worker_count > 1 and len(materialized) <= worker_count else None

    def wrapped(item: T) -> dict[str, Any]:
        if barrier is not None:
            barrier.wait(timeout=timeout_seconds)
        started = time.perf_counter()
        try:
            value = fn(item)
            return {"ok": True, "item": item, "value": value, "duration_ms": int((time.perf_counter() - started) * 1000)}
        except Exception as exc:  # noqa: BLE001 - stress harness should aggregate failures.
            return {
                "ok": False,
                "item": item,
                "error": f"{type(exc).__name__}: {exc}",
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix=f"bmd-{name}") as executor:
        futures = [executor.submit(wrapped, item) for item in materialized]
        for future in as_completed(futures):
            results.append(future.result())
    failed = sum(1 for result in results if not result.get("ok"))
    summary = {
        "name": name,
        "attempted": len(materialized),
        "ok": len(results) - failed,
        "failed": failed,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
    if failed:
        summary["sample_errors"] = [result["error"] for result in results if not result.get("ok")][:5]
    return summary, results


def _db_summary(config: RuntimeConfig) -> dict[str, Any]:
    with connect(config.db_path) as conn:
        tables = [
            "documents",
            "visits",
            "visit_events",
            "snapshots",
            "chunks",
            "media_artifacts",
            "media_fetch_tasks",
            "audit_events",
        ]
        counts = {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        chunks_missing_fts = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM chunks c
                LEFT JOIN chunks_fts f ON f.chunk_id = c.id
                WHERE f.chunk_id IS NULL
                """
            ).fetchone()[0]
        )
        media_statuses = {
            row["capture_status"]: int(row["n"])
            for row in conn.execute("SELECT capture_status, COUNT(*) AS n FROM media_artifacts GROUP BY capture_status").fetchall()
        }
        task_statuses = {
            row["status"]: int(row["n"])
            for row in conn.execute("SELECT status, COUNT(*) AS n FROM media_fetch_tasks GROUP BY status").fetchall()
        }
        audit_events = {
            row["event_type"]: int(row["n"])
            for row in conn.execute("SELECT event_type, COUNT(*) AS n FROM audit_events GROUP BY event_type").fetchall()
        }
    return {
        "counts": counts,
        "integrity_check": integrity,
        "chunks_missing_fts": chunks_missing_fts,
        "media_statuses": media_statuses,
        "media_task_statuses": task_statuses,
        "audit_event_types": audit_events,
    }


def _phase_errors(phase_results: list[dict[str, Any]]) -> list[str]:
    return [str(result.get("error")) for result in phase_results if not result.get("ok")]


def run_concurrency_stress(options: StressOptions | None = None, **overrides: Any) -> dict[str, Any]:
    """Run a bounded deterministic contention exercise against one SQLite DB.

    The harness uses an isolated runtime root by default. It drives the public HTTP
    API for captures, lifecycle events, reads, and media blob uploads while running
    media-worker passes in parallel through separate SQLite connections.
    """
    base_options = options or StressOptions()
    if overrides:
        base_options = replace(base_options, **overrides)
    selected = StressOptions(
        captures=_clamp_int(base_options.captures, minimum=1, maximum=500),
        reader_rounds=_clamp_int(base_options.reader_rounds, minimum=0, maximum=1000),
        media_worker_runs=_clamp_int(base_options.media_worker_runs, minimum=0, maximum=200),
        max_workers=_clamp_int(base_options.max_workers, minimum=1, maximum=128),
        timeout_seconds=max(1.0, float(base_options.timeout_seconds)),
        token=base_options.token or TOKEN,
        policy_mode=base_options.policy_mode,
        runtime_root=base_options.runtime_root,
        keep_runtime=base_options.keep_runtime,
    )

    if selected.runtime_root is None and selected.keep_runtime:
        runtime_context = nullcontext(tempfile.mkdtemp(prefix="bmd-concurrency-stress-"))
    elif selected.runtime_root is None:
        runtime_context = tempfile.TemporaryDirectory(prefix="bmd-concurrency-stress-")
    else:
        runtime_context = nullcontext(None)
    with runtime_context as temp_root:
        runtime_root = Path(selected.runtime_root or temp_root).resolve()
        config = load_config(
            runtime_root=runtime_root,
            test_mode=True,
            token=selected.token,
            host="127.0.0.1",
            port=0,
            policy_mode=selected.policy_mode,
        )
        config = replace(config, media_fetch_on_capture=False)
        server = make_server(config)
        thread = threading.Thread(target=server.serve_forever, name="bmd-stress-server", daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        started = time.perf_counter()
        try:
            capture_phase, capture_results = _run_concurrent(
                "captures",
                range(selected.captures),
                lambda index: _json_request("POST", f"{base_url}/capture", token=selected.token, body=_capture_payload(index), timeout=selected.timeout_seconds)[1],
                max_workers=selected.max_workers,
                timeout_seconds=selected.timeout_seconds,
            )
            captures = [result["value"] for result in capture_results if result.get("ok") and result.get("value", {}).get("stored")]

            upload_inputs: list[tuple[int, dict[str, Any]]] = []
            for index, capture in enumerate(captures):
                artifacts = capture.get("media_artifacts") or []
                if artifacts:
                    upload_inputs.append((index, capture))

            def lifecycle_task(item: tuple[int, dict[str, Any]]) -> dict[str, Any]:
                index, capture = item
                return _json_request(
                    "POST",
                    f"{base_url}/visit-events",
                    token=selected.token,
                    body=_event_payload(capture, index),
                    timeout=selected.timeout_seconds,
                )[1]

            def upload_task(item: tuple[int, dict[str, Any]]) -> dict[str, Any]:
                index, capture = item
                artifact_id = capture["media_artifacts"][0]["artifact_id"]
                deadline = time.monotonic() + selected.timeout_seconds
                capacity_rejections = 0
                while True:
                    try:
                        response = _binary_request(
                            "PUT",
                            f"{base_url}/media-artifacts/{urllib.parse.quote(artifact_id, safe='')}/blob",
                            token=selected.token,
                            body=f"raw-upload-{index}".encode(),
                            content_type="image/png",
                            headers={
                                "X-BMD-Document-ID": capture["document_id"],
                                "X-BMD-Snapshot-ID": capture["snapshot_id"],
                            },
                            timeout=selected.timeout_seconds,
                        )[1]
                        return {"response": response, "capacity_rejections": capacity_rejections}
                    except urllib.error.HTTPError as exc:
                        error_body = exc.read().decode("utf-8", errors="replace")
                        if exc.code != 503 or "media resource budget" not in error_body.lower():
                            raise
                        capacity_rejections += 1
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("media upload remained capacity-limited") from exc
                        time.sleep(min(0.005 * (2 ** min(capacity_rejections - 1, 5)), remaining))

            def reader_task(index: int) -> dict[str, Any]:
                q = urllib.parse.urlencode({"q": SHARED_NEEDLE, "limit": "5"})
                _, search = _json_request("GET", f"{base_url}/search?{q}", token=selected.token, timeout=selected.timeout_seconds)
                _, recent = _json_request("GET", f"{base_url}/recent?limit=5", token=selected.token, timeout=selected.timeout_seconds)
                detail_count = 0
                if captures:
                    capture = captures[index % len(captures)]
                    doc_id = urllib.parse.quote(capture["document_id"], safe="")
                    _, detail = _json_request("GET", f"{base_url}/documents/{doc_id}", token=selected.token, timeout=selected.timeout_seconds)
                    detail_count = len(detail.get("snapshots") or [])
                _, queue = _json_request("GET", f"{base_url}/media-artifacts/queue-status?limit=20", token=selected.token, timeout=selected.timeout_seconds)
                return {
                    "search_results": len(search.get("results") or []),
                    "recent_results": len(recent.get("results") or []),
                    "detail_snapshots": detail_count,
                    "queue_artifacts": dict(queue.get("artifacts") or {}),
                }

            def worker_task(index: int) -> dict[str, Any]:
                with connect(config.db_path) as conn:
                    return run_media_worker_once(conn, config, worker_id=f"stress-worker-{index:04d}", limit=max(1, selected.captures))

            mixed_items: list[tuple[str, Any]] = []
            mixed_items.extend(("lifecycle", item) for item in enumerate(captures))
            mixed_items.extend(("upload", item) for item in upload_inputs)
            mixed_items.extend(("reader", index) for index in range(selected.reader_rounds))
            mixed_items.extend(("media_worker", index) for index in range(selected.media_worker_runs))

            op_counter = Counter(kind for kind, _ in mixed_items)

            def mixed_task(item: tuple[str, Any]) -> dict[str, Any]:
                kind, payload = item
                if kind == "lifecycle":
                    value = lifecycle_task(payload)
                elif kind == "upload":
                    value = upload_task(payload)
                elif kind == "reader":
                    value = reader_task(payload)
                elif kind == "media_worker":
                    value = worker_task(payload)
                else:
                    raise ValueError(f"unknown mixed stress operation: {kind}")
                return {"operation": kind, "result": value}

            mixed_phase, mixed_results = _run_concurrent(
                "mixed",
                mixed_items,
                mixed_task,
                max_workers=selected.max_workers,
                timeout_seconds=selected.timeout_seconds,
            )
            db = _db_summary(config)
            errors = _phase_errors(capture_results) + _phase_errors(mixed_results)
            mixed_ok_by_kind = Counter(
                result["value"]["operation"] for result in mixed_results if result.get("ok") and isinstance(result.get("value"), dict)
            )
            mixed_failed_by_kind = Counter(result["item"][0] for result in mixed_results if not result.get("ok"))
            worker_summaries = [
                result["value"]["result"]
                for result in mixed_results
                if result.get("ok") and result.get("value", {}).get("operation") == "media_worker"
            ]
            upload_summaries = [
                result["value"]["result"]
                for result in mixed_results
                if result.get("ok") and result.get("value", {}).get("operation") == "upload"
            ]
            hard_failures: list[str] = []
            if errors:
                hard_failures.append(f"{len(errors)} stress operations failed")
            if capture_phase["ok"] != selected.captures:
                hard_failures.append("not all capture operations completed")
            if db["integrity_check"] != "ok":
                hard_failures.append(f"sqlite integrity_check={db['integrity_check']}")
            if db["chunks_missing_fts"]:
                hard_failures.append(f"{db['chunks_missing_fts']} chunks missing FTS rows")
            if db["counts"]["documents"] != selected.captures:
                hard_failures.append(f"expected {selected.captures} documents, got {db['counts']['documents']}")
            if db["counts"]["visit_events"] < len(captures):
                hard_failures.append("lifecycle event count lower than successful capture count")
            if mixed_ok_by_kind["upload"] != len(upload_inputs):
                hard_failures.append("not all capacity-limited media uploads completed after retry")

            result = {
                "ok": not hard_failures,
                "summary": {
                    "status": "ok" if not hard_failures else "error",
                    "errors": hard_failures,
                    "operation_errors": errors[:10],
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                },
                "parameters": {
                    "captures": selected.captures,
                    "reader_rounds": selected.reader_rounds,
                    "media_worker_runs": selected.media_worker_runs,
                    "max_workers": selected.max_workers,
                    "timeout_seconds": selected.timeout_seconds,
                    "policy_mode": selected.policy_mode,
                    "isolated_runtime": base_options.runtime_root is None,
                },
                "phases": {"captures": capture_phase, "mixed": mixed_phase},
                "mixed_operations": {
                    "attempted_by_kind": dict(sorted(op_counter.items())),
                    "ok_by_kind": dict(sorted(mixed_ok_by_kind.items())),
                    "failed_by_kind": dict(sorted(mixed_failed_by_kind.items())),
                    "capacity_rejections": sum(
                        int(summary.get("capacity_rejections") or 0) for summary in upload_summaries
                    ),
                },
                "media_worker": {
                    "runs": len(worker_summaries),
                    "attempted": sum(int(summary.get("attempted") or 0) for summary in worker_summaries),
                    "stored": sum(int(summary.get("stored") or 0) for summary in worker_summaries),
                    "failed": sum(int(summary.get("failed") or 0) for summary in worker_summaries),
                    "skipped": sum(int(summary.get("skipped") or 0) for summary in worker_summaries),
                },
                "database": db,
            }
            if selected.keep_runtime or base_options.runtime_root is not None:
                result["runtime_root"] = str(runtime_root)
            return result
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="browser-memory-concurrency-stress")
    parser.add_argument("--runtime-root", type=Path, help="Runtime root to use. Defaults to a temporary isolated root.")
    parser.add_argument("--keep-runtime", action="store_true", help="Keep and report the temporary runtime root instead of deleting it.")
    parser.add_argument("--captures", type=int, default=StressOptions.captures)
    parser.add_argument("--reader-rounds", type=int, default=StressOptions.reader_rounds)
    parser.add_argument("--media-worker-runs", type=int, default=StressOptions.media_worker_runs)
    parser.add_argument("--max-workers", type=int, default=StressOptions.max_workers)
    parser.add_argument("--timeout", type=float, default=StressOptions.timeout_seconds)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--policy-mode", choices=["all", "recall", "balanced", "strict"], default="all")
    parser.add_argument("--no-fail", action="store_true", help="Print the report and exit 0 even when the harness finds errors.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = run_concurrency_stress(
        StressOptions(
            captures=args.captures,
            reader_rounds=args.reader_rounds,
            media_worker_runs=args.media_worker_runs,
            max_workers=args.max_workers,
            timeout_seconds=args.timeout,
            token=args.token,
            policy_mode=args.policy_mode,
            runtime_root=args.runtime_root,
            keep_runtime=args.keep_runtime,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if (args.no_fail or result.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
