from __future__ import annotations

from dataclasses import dataclass
from re import Pattern
from re import compile as compile_pattern
from urllib.parse import unquote


@dataclass(frozen=True)
class Route:
    method: str
    name: str
    path: str
    auth_required: bool = True
    parameter_names: tuple[str, ...] = ()
    pattern: Pattern[str] | None = None

    def match(self, method: str, path: str) -> dict[str, str] | None:
        if method != self.method:
            return None
        if self.pattern is None:
            return {} if path == self.path else None
        matched = self.pattern.fullmatch(path)
        if matched is None:
            return None
        return {
            name: unquote(value)
            for name, value in zip(self.parameter_names, matched.groups(), strict=True)
        }


@dataclass(frozen=True)
class RouteMatch:
    route: Route
    parameters: dict[str, str]


ROUTES: tuple[Route, ...] = (
    Route("GET", "health", "/health", auth_required=False),
    Route("GET", "ready", "/ready"),
    Route("GET", "search", "/search"),
    Route("GET", "recent", "/recent"),
    Route("GET", "timeline", "/timeline"),
    Route("GET", "document-detail", "/documents/{document_id}", parameter_names=("document_id",), pattern=compile_pattern(r"/documents/(.*)")),
    Route("GET", "snapshot-detail", "/snapshots/{snapshot_id}", parameter_names=("snapshot_id",), pattern=compile_pattern(r"/snapshots/(.*)")),
    Route("GET", "media-queue-status", "/media-artifacts/queue-status"),
    Route("GET", "media-detail", "/media-artifacts/{artifact_id}", parameter_names=("artifact_id",), pattern=compile_pattern(r"/media-artifacts/(.*)")),
    Route("GET", "doctor", "/doctor"),
    Route("GET", "policy-rules-list", "/policy/rules"),
    Route("GET", "policy-evaluate", "/policy/evaluate"),
    Route("PUT", "media-blob-put", "/media-artifacts/{artifact_id}/blob", parameter_names=("artifact_id",), pattern=compile_pattern(r"/media-artifacts/(.*)/blob")),
    Route("POST", "media-cache-purge", "/media-artifacts/purge-cache"),
    Route("POST", "media-fetch-pending", "/media-artifacts/fetch-pending"),
    Route("POST", "media-artifact-store", "/media-artifacts"),
    Route("POST", "visit-event-store", "/visit-events"),
    Route("POST", "capture-store", "/capture"),
    Route("POST", "forget", "/forget"),
    Route("POST", "policy-rule-create", "/policy/rules"),
    Route("DELETE", "policy-rule-delete", "/policy/rules/{rule_id}", parameter_names=("rule_id",), pattern=compile_pattern(r"/policy/rules/(.*)")),
)


def match_route(method: str, path: str) -> RouteMatch | None:
    normalized_method = method.upper()
    for route in ROUTES:
        parameters = route.match(normalized_method, path)
        if parameters is not None:
            return RouteMatch(route=route, parameters=parameters)
    return None
