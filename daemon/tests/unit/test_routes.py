import pytest
from browser_memory_daemon.routes import ROUTES, match_route


@pytest.mark.parametrize(
    ("method", "path", "name", "parameters", "auth_required"),
    [
        ("GET", "/health", "health", {}, False),
        ("GET", "/ready", "ready", {}, True),
        ("GET", "/search", "search", {}, True),
        ("GET", "/recent", "recent", {}, True),
        ("GET", "/timeline", "timeline", {}, True),
        ("GET", "/exports/x-observations", "x-observation-export", {}, True),
        ("GET", "/documents/doc%2Fencoded", "document-detail", {"document_id": "doc/encoded"}, True),
        ("GET", "/snapshots/snap-1", "snapshot-detail", {"snapshot_id": "snap-1"}, True),
        ("GET", "/media-artifacts/queue-status", "media-queue-status", {}, True),
        ("GET", "/media-artifacts/media-1", "media-detail", {"artifact_id": "media-1"}, True),
        ("GET", "/doctor", "doctor", {}, True),
        ("GET", "/policy/rules", "policy-rules-list", {}, True),
        ("GET", "/policy/evaluate", "policy-evaluate", {}, True),
        ("PUT", "/media-artifacts/media%2Fencoded/blob", "media-blob-put", {"artifact_id": "media/encoded"}, True),
        ("POST", "/media-artifacts/purge-cache", "media-cache-purge", {}, True),
        ("POST", "/media-artifacts/fetch-pending", "media-fetch-pending", {}, True),
        ("POST", "/media-artifacts", "media-artifact-store", {}, True),
        ("POST", "/visit-events", "visit-event-store", {}, True),
        ("POST", "/capture", "capture-store", {}, True),
        ("POST", "/forget", "forget", {}, True),
        ("POST", "/policy/rules", "policy-rule-create", {}, True),
        ("DELETE", "/policy/rules/rule%2Fencoded", "policy-rule-delete", {"rule_id": "rule/encoded"}, True),
    ],
)
def test_route_descriptors_characterize_every_current_api_endpoint(method, path, name, parameters, auth_required):
    matched = match_route(method, path)
    assert matched is not None
    assert matched.route.name == name
    assert matched.parameters == parameters
    assert matched.route.auth_required is auth_required


def test_route_matching_preserves_static_precedence_and_method_boundaries():
    queue = match_route("GET", "/media-artifacts/queue-status")
    assert queue is not None
    assert queue.route.name == "media-queue-status"
    assert queue.parameters == {}

    assert match_route("POST", "/health") is None
    assert match_route("PATCH", "/health") is None
    assert match_route("GET", "/does-not-exist") is None
    assert match_route("GET", "/ui") is None


def test_route_catalog_names_and_method_path_pairs_are_unique():
    assert len({route.name for route in ROUTES}) == len(ROUTES)
    assert len({(route.method, route.path) for route in ROUTES}) == len(ROUTES)
