from __future__ import annotations

import sqlite3

_DOMAIN_CONFLICT_MESSAGES = {
    "observation_id conflicts with an existing capture",
    "visit_id conflicts with an existing navigation",
}


class APIError(Exception):
    def __init__(self, *, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def payload(self, extra: dict[str, object] | None = None) -> dict[str, object]:
        payload = dict(extra or {})
        payload.update({"error": self.message, "error_code": self.code})
        return payload


class ValidationError(APIError):
    def __init__(self, message: str = "invalid request") -> None:
        super().__init__(status=400, code="invalid_request", message=message)


class UnauthorizedError(APIError):
    def __init__(self, message: str = "unauthorized") -> None:
        super().__init__(status=401, code="unauthorized", message=message)


class ForbiddenError(APIError):
    def __init__(self, message: str = "forbidden") -> None:
        super().__init__(status=403, code="forbidden", message=message)


class NotFoundError(APIError):
    def __init__(self, message: str = "not found") -> None:
        super().__init__(status=404, code="not_found", message=message)


class ConflictError(APIError):
    def __init__(self, message: str = "request conflicts with existing state") -> None:
        super().__init__(status=409, code="conflict", message=message)


class ResourceUnavailableError(APIError):
    def __init__(self, message: str = "resource temporarily unavailable") -> None:
        super().__init__(status=503, code="resource_unavailable", message=message)


class DatabaseBusyError(APIError):
    def __init__(self) -> None:
        super().__init__(status=503, code="database_busy", message="database temporarily unavailable")


class DatabaseUnavailableError(APIError):
    def __init__(self) -> None:
        super().__init__(status=503, code="database_unavailable", message="database temporarily unavailable")


class InternalError(APIError):
    def __init__(self) -> None:
        super().__init__(status=500, code="internal_error", message="internal server error")


class UnsupportedMethodError(APIError):
    def __init__(self, message: str) -> None:
        super().__init__(status=501, code="unsupported_method", message=message)


def _key_error_message(error: KeyError) -> str:
    if error.args:
        return str(error.args[0])
    return "not found"


def classify_exception(error: Exception) -> APIError:
    if isinstance(error, APIError):
        return error
    if isinstance(error, sqlite3.IntegrityError):
        return ConflictError()
    if isinstance(error, sqlite3.OperationalError):
        detail = str(error).lower()
        if "locked" in detail or "busy" in detail:
            return DatabaseBusyError()
        return DatabaseUnavailableError()
    if isinstance(error, KeyError):
        return NotFoundError(_key_error_message(error))
    if isinstance(error, ValueError):
        message = str(error) or "invalid request"
        if message in _DOMAIN_CONFLICT_MESSAGES:
            return ConflictError(message)
        return ValidationError(message)
    if isinstance(error, OSError):
        return ResourceUnavailableError()
    return InternalError()
