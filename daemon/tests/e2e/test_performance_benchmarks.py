from __future__ import annotations

import json

from browser_memory_daemon.performance_benchmarks import main


def test_performance_benchmark_json_output_is_structured(tmp_path, capsys):
    runtime_root = tmp_path / "benchmark-json"

    assert main([
        "--small",
        "--json",
        "--runtime-root",
        str(runtime_root),
        "--captures",
        "8",
        "--read-repetitions",
        "2",
        "--media-worker-limit",
        "8",
    ]) == 0

    output = capsys.readouterr().out
    data = json.loads(output)

    assert data["ok"] is True
    assert data["dataset"]["captures"] == 8
    assert data["dataset"]["captured_text_source"].startswith("deterministic synthetic generator")
    assert data["runtime"]["runtime_root_retained"] is True
    assert data["benchmarks"]["ingest"]["captures"] == 8
    assert data["benchmarks"]["read_surfaces"]["search"]["with_audit"]["samples"] == 2
    assert "audit_write_overhead_mean_ms_estimate" in data["benchmarks"]["read_surfaces"]["search"]
    assert data["benchmarks"]["media_worker"]["task_selection"]["selected_task_count"] == 4
    assert data["benchmarks"]["media_worker"]["run_once_summary"]["attempted"] == 4
    assert data["benchmarks"]["media_worker"]["run_once_summary"]["stored"] == 4
    assert data["storage"]["db_bytes"] > 0
    assert data["storage"]["wal_bytes"] >= 0
    assert data["storage"]["media_bytes"] > 0
    assert data["storage"]["total_sidecar_bytes"] > 0
    assert data["budgets"]["advisory"] is True


def test_performance_benchmark_human_summary_is_compact(tmp_path, capsys):
    runtime_root = tmp_path / "benchmark-human"

    assert main([
        "--runtime-root",
        str(runtime_root),
        "--captures",
        "6",
        "--read-repetitions",
        "1",
        "--media-every",
        "0",
        "--media-worker-limit",
        "4",
    ]) == 0

    output = capsys.readouterr().out

    assert "BMD performance benchmark summary" in output
    assert "dataset: captures=6" in output
    assert "search+audit:" in output
    assert "media worker:" in output
    assert "storage:" in output
    assert "budgets: advisory" in output
