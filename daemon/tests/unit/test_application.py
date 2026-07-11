from dataclasses import replace
from pathlib import Path

import browser_memory_daemon.app as app_module
from browser_memory_daemon.application import MemoryApplication
from browser_memory_daemon.config import load_config


def test_app_module_is_only_the_http_composition_root():
    assert app_module.__file__ is not None
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    assert "MemoryApplication(config, database_ready=True)" in source
    assert "create_http_server(config, application)" in source
    for forbidden_domain_import in [".forget", ".ingest", ".media", ".ops", ".policy", ".search"]:
        assert forbidden_domain_import not in source


def test_application_capture_and_read_use_cases_run_without_http_handler(tmp_path):
    config = load_config(
        runtime_root=tmp_path,
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )
    config = replace(config, media_fetch_on_capture=False)
    application = MemoryApplication(config)

    captured = application.capture(
        {
            "visit_id": "application-visit-1",
            "url": "https://example.org/application-layer",
            "title": "Application layer",
            "text": "Application use cases execute without an HTTP request object.",
        }
    )
    assert captured["stored"] is True

    results = application.search("Application use cases", limit=10)
    assert [row["snapshot_id"] for row in results] == [captured["snapshot_id"]]
    detail = application.snapshot_detail(captured["snapshot_id"])
    assert "Application use cases execute" in detail["text"]


def test_application_policy_blocking_remains_a_use_case_decision(tmp_path):
    config = load_config(
        runtime_root=tmp_path,
        test_mode=True,
        token="test-token",
        policy_mode="all",
    )
    application = MemoryApplication(config)
    application.create_policy_rule(rule_type="domain", pattern="blocked.example", action="block")

    result = application.capture(
        {
            "url": "https://blocked.example/private",
            "title": "Blocked",
            "text": "This body must not be stored.",
        }
    )
    assert result == {
        "stored": False,
        "blocked": True,
        "reason": "policy-rule:block-domain:blocked.example",
    }
    assert application.search("This body must not be stored", limit=10) == []
