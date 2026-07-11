# ADR-0055: Add a redaction-safe HTTP request envelope

- Status: accepted
- Date: 2026-07-10
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0012, ADR-0053, ADR-0054

## Context

The loopback HTTP adapter had no per-request correlation identifier, suppressed ordinary access logs entirely, and applied only a subset of browser security headers depending on response type. Diagnostic logging must support local journald operations without recording request paths, query strings, URLs, headers, bearer values, or captured payloads.

## Decision

1. Generate an opaque server-side `req_` identifier for every HTTP request. Do not trust or reflect a caller-supplied request identifier.
2. Return the identifier in `X-Request-ID` on JSON, UI/static, binary, error, and OPTIONS responses. Include the same identifier as `request_id` in compatible JSON error bodies and expose the header through CORS.
3. Apply `Cache-Control: no-store`, content-type, frame, referrer, permissions, and content-security protections through one common response boundary. Use a restrictive API policy and a separate same-origin UI policy that permits the existing bootstrap JSON script and local UI assets.
4. Emit exactly one compact JSON telemetry event per completed response to stderr for journald capture. The event contains only request ID, HTTP method, descriptor route name, status, integer latency, and safe error code.
5. Never log raw paths, query strings, origins, client addresses, headers, bearer values, request/response bodies, captured URLs, or exception prose. Unknown or unsafe route labels collapse to `unknown`.
6. Telemetry failure must not change the HTTP result.

## Consequences

- Operators can correlate client errors with local daemon telemetry without exposing captured evidence.
- All response classes now carry the same baseline security envelope.
- Existing successful JSON bodies remain unchanged; error bodies gain only the additive `request_id` field.
- The UI retains same-origin operation under an explicit CSP rather than sharing the API's `default-src 'none'` policy.
- `REQ-040` remains planned until bounded upload/download disconnect handling and the remaining HTTP/application decomposition close.

## Verification

- `daemon/tests/e2e/test_http_api.py::test_http_request_envelope_adds_unique_ids_and_security_headers_to_every_response_kind`
- `daemon/tests/e2e/test_http_api.py::test_http_structured_request_telemetry_contains_only_redaction_safe_fields`
- Media response characterization in `daemon/tests/e2e/test_http_api.py` verifies the binary response envelope.
