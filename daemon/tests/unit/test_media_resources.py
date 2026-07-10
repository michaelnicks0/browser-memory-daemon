from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import browser_memory_daemon.media_fetch as media_fetch
import pytest
from browser_memory_daemon.config import load_config
from browser_memory_daemon.media_models import media_capture_status_for_fetch_reason
from browser_memory_daemon.media_resources import (
    MediaResourceBudget,
    MediaResourceUnavailable,
    media_resource_budget,
)


def test_media_resource_budget_enforces_request_and_byte_caps_and_releases():
    budget = MediaResourceBudget(max_inflight_bytes=10, max_concurrent_requests=1)
    with budget.acquire(byte_count=7, request_count=1, timeout=0):
        assert budget.snapshot() == {
            "max_inflight_bytes": 10,
            "max_concurrent_requests": 1,
            "inflight_bytes": 7,
            "active_requests": 1,
        }
        with pytest.raises(MediaResourceUnavailable, match="budget"):
            budget.acquire(byte_count=4, request_count=0, timeout=0)
        with pytest.raises(MediaResourceUnavailable, match="budget"):
            budget.acquire(byte_count=0, request_count=1, timeout=0)
    assert budget.snapshot()["inflight_bytes"] == 0
    assert budget.snapshot()["active_requests"] == 0


def test_media_resource_budget_serializes_waiters_without_leaking_capacity():
    budget = MediaResourceBudget(max_inflight_bytes=8, max_concurrent_requests=1)
    holding = Event()
    release = Event()

    def first() -> str:
        with budget.acquire(byte_count=8, request_count=1, timeout=1):
            holding.set()
            assert release.wait(timeout=1)
            return "first"

    def second() -> str:
        assert holding.wait(timeout=1)
        with pytest.raises(MediaResourceUnavailable, match="budget"):
            budget.acquire(byte_count=1, request_count=1, timeout=0.01)
        release.set()
        with budget.acquire(byte_count=1, request_count=1, timeout=1):
            return "second"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(first)
        second_future = pool.submit(second)
        assert {first_future.result(), second_future.result()} == {"first", "second"}
    assert budget.snapshot()["inflight_bytes"] == 0
    assert budget.snapshot()["active_requests"] == 0


def test_guarded_fetch_reports_retryable_global_request_pressure(tmp_path, monkeypatch):
    cfg = replace(
        load_config(runtime_root=tmp_path, test_mode=True, token="test-token", policy_mode="all"),
        max_media_inflight_bytes=100,
        max_media_concurrent_requests=1,
    )
    monkeypatch.setattr(
        media_fetch,
        "_PUBLIC_FETCH_RESOLVER",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    budget = media_resource_budget(cfg)
    with budget.acquire(byte_count=0, request_count=1, timeout=0):
        content, mime_type, reason = media_fetch._fetch_media_bytes(
            "https://example.com/image.png",
            "https://example.org/page",
            media_type="image",
            max_bytes=50,
            timeout_seconds=0.01,
            config=cfg,
        )
    assert content == b""
    assert mime_type == ""
    assert reason == "media-resource-budget"
    assert media_capture_status_for_fetch_reason(reason) == "retrying"
    assert budget.snapshot()["inflight_bytes"] == 0
