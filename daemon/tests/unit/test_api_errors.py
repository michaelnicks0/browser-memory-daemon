import sqlite3

import pytest
from browser_memory_daemon.api_errors import (
    APIError,
    ConflictError,
    DatabaseBusyError,
    InternalError,
    NotFoundError,
    ResourceUnavailableError,
    ValidationError,
    classify_exception,
)


@pytest.mark.parametrize(
    ("error", "status", "code", "message"),
    [
        (ValidationError("invalid selector"), 400, "invalid_request", "invalid selector"),
        (ConflictError("capture conflicts with existing state"), 409, "conflict", "capture conflicts with existing state"),
        (NotFoundError("snapshot not found"), 404, "not_found", "snapshot not found"),
        (ResourceUnavailableError("media resource budget unavailable"), 503, "resource_unavailable", "media resource budget unavailable"),
        (DatabaseBusyError(), 503, "database_busy", "database temporarily unavailable"),
        (InternalError(), 500, "internal_error", "internal server error"),
    ],
)
def test_typed_api_errors_have_stable_status_code_and_compatible_message(error, status, code, message):
    assert error.status == status
    assert error.code == code
    assert error.message == message
    assert error.payload() == {"error": message, "error_code": code}


def test_exception_classification_preserves_safe_client_errors_and_sanitizes_internal_failures():
    invalid = classify_exception(ValueError("limit must be numeric"))
    domain_conflict = classify_exception(ValueError("observation_id conflicts with an existing capture"))
    missing = classify_exception(KeyError("document not found"))
    conflict = classify_exception(sqlite3.IntegrityError("UNIQUE constraint failed: private_table.secret"))
    busy = classify_exception(sqlite3.OperationalError("database is locked at /private/runtime.sqlite3"))
    internal = classify_exception(RuntimeError("token=secret internal path=/private/runtime.sqlite3"))

    assert invalid.payload() == {"error": "limit must be numeric", "error_code": "invalid_request"}
    assert domain_conflict.payload() == {"error": "observation_id conflicts with an existing capture", "error_code": "conflict"}
    assert missing.payload() == {"error": "document not found", "error_code": "not_found"}
    assert conflict.payload() == {"error": "request conflicts with existing state", "error_code": "conflict"}
    assert busy.payload() == {"error": "database temporarily unavailable", "error_code": "database_busy"}
    assert internal.payload() == {"error": "internal server error", "error_code": "internal_error"}


def test_exception_classification_retains_existing_typed_errors():
    expected = APIError(status=418, code="test_error", message="safe test message")
    assert classify_exception(expected) is expected
