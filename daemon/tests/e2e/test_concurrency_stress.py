import json

from browser_memory_daemon.concurrency_stress import StressOptions, main, run_concurrency_stress


def test_concurrency_stress_harness_exercises_shared_sqlite_db(tmp_path):
    result = run_concurrency_stress(
        StressOptions(
            runtime_root=tmp_path,
            captures=4,
            reader_rounds=4,
            media_worker_runs=2,
            max_workers=8,
            timeout_seconds=20,
        )
    )

    assert result["ok"] is True
    assert result["summary"]["errors"] == []
    assert result["phases"]["captures"]["ok"] == 4
    assert result["mixed_operations"]["attempted_by_kind"] == {
        "lifecycle": 4,
        "media_worker": 2,
        "reader": 4,
        "upload": 4,
    }
    assert result["mixed_operations"]["failed_by_kind"] == {}
    assert result["database"]["integrity_check"] == "ok"
    assert result["database"]["chunks_missing_fts"] == 0
    assert result["database"]["counts"]["documents"] == 4
    assert result["database"]["counts"]["visit_events"] == 4
    assert result["database"]["media_statuses"] == {"stored": 4}
    assert result["database"]["media_task_statuses"] == {"succeeded": 4}


def test_concurrency_stress_cli_prints_json_for_explicit_runtime(tmp_path, capsys):
    exit_code = main(
        [
            "--runtime-root",
            str(tmp_path),
            "--captures",
            "2",
            "--reader-rounds",
            "1",
            "--media-worker-runs",
            "1",
            "--max-workers",
            "4",
            "--timeout",
            "20",
        ]
    )

    assert exit_code == 0
    rendered = capsys.readouterr().out
    data = json.loads(rendered)
    assert data["ok"] is True
    assert data["parameters"]["captures"] == 2
    assert data["parameters"]["isolated_runtime"] is False
    assert data["runtime_root"] == str(tmp_path.resolve())
