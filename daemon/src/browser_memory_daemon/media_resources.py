from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Condition, Lock
from typing import Any

from .config import RuntimeConfig


class MediaResourceUnavailable(RuntimeError):
    pass


@dataclass
class MediaResourceLease:
    _budget: MediaResourceBudget
    byte_count: int
    request_count: int
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._budget._release(self.byte_count, self.request_count)

    def __enter__(self) -> MediaResourceLease:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()


class MediaResourceBudget:
    def __init__(self, *, max_inflight_bytes: int, max_concurrent_requests: int) -> None:
        self.max_inflight_bytes = max(1, int(max_inflight_bytes))
        self.max_concurrent_requests = max(1, int(max_concurrent_requests))
        self._inflight_bytes = 0
        self._active_requests = 0
        self._condition = Condition()

    def acquire(
        self,
        *,
        byte_count: int,
        request_count: int = 1,
        timeout: float | None = 0,
    ) -> MediaResourceLease:
        selected_bytes = max(0, int(byte_count))
        selected_requests = max(0, int(request_count))
        if selected_bytes > self.max_inflight_bytes or selected_requests > self.max_concurrent_requests:
            raise MediaResourceUnavailable("media resource request exceeds configured budget")
        deadline = None if timeout is None else time.monotonic() + max(0.0, float(timeout))
        with self._condition:
            while (
                self._inflight_bytes + selected_bytes > self.max_inflight_bytes
                or self._active_requests + selected_requests > self.max_concurrent_requests
            ):
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MediaResourceUnavailable("media resource budget is busy")
                self._condition.wait(timeout=remaining)
            self._inflight_bytes += selected_bytes
            self._active_requests += selected_requests
        return MediaResourceLease(self, selected_bytes, selected_requests)

    def _release(self, byte_count: int, request_count: int) -> None:
        with self._condition:
            self._inflight_bytes = max(0, self._inflight_bytes - max(0, int(byte_count)))
            self._active_requests = max(0, self._active_requests - max(0, int(request_count)))
            self._condition.notify_all()

    def snapshot(self) -> dict[str, int]:
        with self._condition:
            return {
                "max_inflight_bytes": self.max_inflight_bytes,
                "max_concurrent_requests": self.max_concurrent_requests,
                "inflight_bytes": self._inflight_bytes,
                "active_requests": self._active_requests,
            }


_REGISTRY_LOCK = Lock()
_REGISTRY: dict[tuple[int, int], MediaResourceBudget] = {}


def media_resource_budget(config: RuntimeConfig) -> MediaResourceBudget:
    key = (int(config.max_media_inflight_bytes), int(config.max_media_concurrent_requests))
    with _REGISTRY_LOCK:
        budget = _REGISTRY.get(key)
        if budget is None:
            budget = MediaResourceBudget(max_inflight_bytes=key[0], max_concurrent_requests=key[1])
            _REGISTRY[key] = budget
        return budget


__all__ = ["MediaResourceBudget", "MediaResourceLease", "MediaResourceUnavailable", "media_resource_budget"]
