from browser_memory_daemon import media
from browser_memory_daemon.media_models import (
    MEDIA_ARTIFACT_STATUSES,
    MEDIA_CAPTURE_STATUSES,
    MEDIA_TASK_STATUSES,
    media_artifact_transition_allowed,
    media_capture_status_for_fetch_reason,
    media_task_transition_allowed,
    normalize_capture_status,
    normalize_task_status,
)
from browser_memory_daemon.media_tasks import media_fetch_task_id


def test_media_facade_preserves_public_state_and_task_symbols():
    assert media.MEDIA_CAPTURE_STATUSES == MEDIA_CAPTURE_STATUSES
    assert media.MEDIA_TASK_STATUSES == MEDIA_TASK_STATUSES
    assert media.normalize_capture_status is normalize_capture_status
    assert media.normalize_task_status is normalize_task_status
    assert media.media_fetch_task_id is media_fetch_task_id


def test_media_state_taxonomy_separates_internal_storage_recovery_states_from_caller_input():
    assert {"purging", "missing"} <= MEDIA_ARTIFACT_STATUSES
    assert {"purging", "missing"}.isdisjoint(MEDIA_CAPTURE_STATUSES)
    assert normalize_capture_status("purging") == "metadata-only"
    assert normalize_capture_status("STORED") == "stored"
    assert normalize_task_status("RETRYING") == "retrying"
    assert normalize_task_status("unknown") == "pending"


def test_media_transition_matrices_preserve_terminal_and_recovery_boundaries():
    assert media_task_transition_allowed("pending", "leased") is True
    assert media_task_transition_allowed("leased", "retrying") is True
    assert media_task_transition_allowed("succeeded", "pending") is False
    assert media_task_transition_allowed("succeeded", "pending", force_reset=True) is True
    assert media_task_transition_allowed("skipped", "leased") is False

    assert media_artifact_transition_allowed("stored", "purging") is True
    assert media_artifact_transition_allowed("purging", "purged") is True
    assert media_artifact_transition_allowed("purged", "stored") is True
    assert media_artifact_transition_allowed("stored", "referenced") is False
    assert media_artifact_transition_allowed("missing", "stored") is True


def test_fetch_reason_classification_is_independent_from_media_facade():
    cases = [
        ("invalid-data-url-payload", "data:image/png;base64,bad", "image", "skipped"),
        ("non-media-content-type", "https://example.test/video", "video", "referenced"),
        ("fetch-status-404", "https://example.test/image.png", "image", "expired"),
        ("fetch-status-429", "https://example.test/image.png", "image", "retrying"),
        ("hls-no-segments", "https://example.test/video.m3u8", "video", "referenced"),
        ("unexpected-worker-error", "https://example.test/image.png", "image", "failed"),
    ]
    for reason, source_url, media_type, expected in cases:
        assert media_capture_status_for_fetch_reason(reason, source_url=source_url, media_type=media_type) == expected
        assert media.media_capture_status_for_fetch_reason(reason, source_url=source_url, media_type=media_type) == expected
