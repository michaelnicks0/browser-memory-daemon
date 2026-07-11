# ADR-0054: Use typed compatible HTTP errors and sanitize internal failures

- Status: accepted
- Date: 2026-07-10
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0012, ADR-0015, ADR-0053

## Context

The standard-library HTTP adapter historically converted most exceptions to HTTP 400 and exposed `str(exception)` directly. That made database contention and internal failures look like client mistakes and could disclose internal paths, SQLite details, or other implementation data. Existing extension, UI, and CLI clients still depend on the top-level `error` string.

## Decision

1. Keep the top-level `error` string in every JSON error response and add a stable `error_code` field.
2. Define typed validation, authorization, forbidden, not-found, conflict, resource-unavailable, database-busy/database-unavailable, unsupported-method, and internal errors in `api_errors.py`.
3. Map known client validation messages to 400, missing records to 404, capture identity conflicts and SQLite integrity conflicts to 409, resource and database availability failures to 503, and unexpected failures to 500.
4. Expose safe validation and known resource messages, but replace SQLite implementation details and unexpected exception text with bounded generic messages.
5. Keep endpoint paths, successful response bodies, auth ordering, and existing human-readable error strings compatible wherever the old string was safe.
6. Defer request IDs, structured request telemetry, and universal transport headers to the next HTTP slice.

## Consequences

- Clients can branch on stable machine-readable codes without parsing prose.
- Database contention is retryable 503 rather than misleading 400.
- Unexpected failures no longer disclose raw exception text.
- Existing clients that read only `error` remain compatible.
- `REQ-040` remains planned until request IDs, common security headers, structured telemetry, and remaining streaming boundaries are complete.
