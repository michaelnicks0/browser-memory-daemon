from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from browser_memory_daemon.config import RuntimeConfig
from browser_memory_daemon.performance_benchmarks import _assert_benchmark_paths_contained, main


def _assert_runtime_paths_under_root(runtime: dict[str, object], runtime_root: Path) -> None:
    root = runtime_root.resolve()
    for key in [
        "config_root",
        "data_root",
        "state_root",
        "blob_root",
        "db_path",
        "clean_text_root",
        "raw_html_root",
        "media_root",
        "audit_log_path",
    ]:
        assert Path(str(runtime[key])).resolve().is_relative_to(root), key


def _benchmark_subprocess_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    daemon_src = Path(__file__).resolve().parents[2] / "src"
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / "config"),
            "XDG_DATA_HOME": str(home / "data"),
            "XDG_STATE_HOME": str(home / "state"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": f"{daemon_src}{os.pathsep}{env.get('PYTHONPATH', '')}" if env.get("PYTHONPATH") else str(daemon_src),
        }
    )
    return env


def test_performance_benchmark_path_invariant_rejects_blob_escape(tmp_path):
    runtime_root = tmp_path / "runtime"
    outside_root = tmp_path / "outside"
    cfg = RuntimeConfig(
        api_token="benchmark-token",
        config_root=runtime_root / "config",
        data_root=runtime_root / "data",
        state_root=runtime_root / "state",
        blob_root=outside_root / "blobs",
    )

    with pytest.raises(RuntimeError, match="blob_root"):
        _assert_benchmark_paths_contained(cfg, runtime_root)

    assert not outside_root.exists()


def test_performance_benchmark_subprocess_does_not_write_default_home_blob_root(tmp_path):
    outside_home = tmp_path / "outside-home"
    outside_home.mkdir()
    runtime_root = tmp_path / "benchmark-runtime"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "browser_memory_daemon.performance_benchmarks",
            "--small",
            "--json",
            "--runtime-root",
            str(runtime_root),
            "--captures",
            "4",
            "--read-repetitions",
            "1",
            "--media-worker-limit",
            "4",
        ],
        check=False,
        env=_benchmark_subprocess_env(outside_home),
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    data = json.loads(completed.stdout)
    _assert_runtime_paths_under_root(data["runtime"], runtime_root)
    assert data["runtime"]["runtime_root_retained"] is True
    assert not (runtime_root / "blobs" / "clean-text").exists()
    assert Path(data["runtime"]["db_path"]).is_file()
    assert not (outside_home / ".local" / "share" / "browser-memory-daemon" / "blobs").exists()


def test_performance_benchmark_temp_runtime_cleanup_stays_inside_tmp_home(tmp_path):
    outside_home = tmp_path / "outside-home"
    outside_home.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "browser_memory_daemon.performance_benchmarks",
            "--small",
            "--json",
            "--captures",
            "4",
            "--read-repetitions",
            "1",
            "--media-worker-limit",
            "4",
        ],
        check=False,
        env=_benchmark_subprocess_env(outside_home),
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    data = json.loads(completed.stdout)
    runtime_root = Path(data["runtime"]["runtime_root"])
    assert data["runtime"]["runtime_root_retained"] is False
    assert not runtime_root.exists()
    assert not (outside_home / ".local" / "share" / "browser-memory-daemon" / "blobs").exists()


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
    _assert_runtime_paths_under_root(data["runtime"], runtime_root)
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
