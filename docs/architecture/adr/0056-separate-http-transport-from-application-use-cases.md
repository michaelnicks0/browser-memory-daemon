# ADR-0056: Separate HTTP transport from application use cases

- Status: accepted
- Date: 2026-07-10
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0014, ADR-0047, ADR-0053, ADR-0054, ADR-0055, REQ-040

## Context

The characterized standard-library HTTP server still owned database initialization checks, transaction and audit boundaries, capture policy decisions, read-model calls, forget execution, media coordination, and background media kickoff inside `BaseHTTPRequestHandler` methods. This coupled every use case to HTTP request/response objects, made direct use-case verification awkward, and left `app.py` as a large mixed transport/domain module rather than a composition root.

The endpoint paths, authentication order, response shapes, typed error mapping, request envelope, media streaming, and extension/UI clients are already compatibility-authoritative. The structural change must preserve those contracts without introducing a web framework, dependency-injection container, generic dispatcher, ORM, event bus, or unit-of-work abstraction.

## Decision

1. `application.py` owns explicit request-independent capture, lifecycle, search/read, forget, policy, doctor, and media use-case methods. It owns database-ready checks, SQLite transaction/audit boundaries, capture policy evaluation, asynchronous post-capture media kickoff, and upload/download resource leases.
2. `http_server.py` owns the `BaseHTTPRequestHandler` adapter, immutable route matching, auth and input parsing, response status selection, common headers, typed error serialization, request telemetry, finite UI/static serving, and bounded body/stream transport behavior.
3. `app.py` is the composition root: initialize the versioned database once, construct `MemoryApplication`, and bind it to the standard-library HTTP server.
4. Use explicit application methods rather than a generic route-to-callable framework. Domain modules remain independently callable by the CLI and workers.
5. Media downloads cross the application boundary as a scoped context-managed stream descriptor so the resource lease and BlobStore handle remain live only while the transport streams the response.
6. Typed application errors may carry an allowlisted structured payload for compatibility-sensitive safe details, such as the existing missing-media artifact summary. Arbitrary exception text remains sanitized by the transport classifier.

## Consequences

- Capture/search/policy behavior can be exercised without constructing an HTTP handler.
- The HTTP adapter no longer imports ingest, search, forget, lifecycle, policy-store, operations, or media-domain functions directly.
- `app.py` has one responsibility and no route or domain behavior.
- The standard-library-first architecture and all existing paths, methods, auth ordering, statuses, response fields, request IDs, security headers, and disconnect behavior remain intact.
- Transaction boundaries remain deliberately local to each explicit use case; this is not a generic repository or unit-of-work layer.

## Verification

- `daemon/tests/unit/test_application.py::test_app_module_is_only_the_http_composition_root`
- `daemon/tests/unit/test_application.py::test_application_capture_and_read_use_cases_run_without_http_handler`
- `daemon/tests/unit/test_application.py::test_application_policy_blocking_remains_a_use_case_decision`
- The focused application, route, typed-error, HTTP transport, full HTTP API, admin API, UI smoke, CLI-admin, and media-worker set passes with 92 tests.
- Ruff and targeted strict Mypy pass for `app.py`, `application.py`, `http_server.py`, and `api_errors.py`.
- The hermetic fast gate passes 239 Python and 69 Node tests at 82.85% measured branch coverage; the broad repository gate passes with the extension build.
- Isolated cached Chrome for Testing passes the `all` and `strict` matrix without using the operator profile.
- The concurrency harness completes 12 captures and 40 mixed operations with zero failures, SQLite integrity `ok`, and all 12 media artifacts/tasks converged to stored/succeeded.
- The synthetic-small benchmark passes with 0.782 ms mean and 1.209 ms p95 ingest across 40 captures; 20 media tasks complete in 176.219 ms and all runtime paths remain under `/tmp`.
- Structurizr validation, 25 complete generated C4 view sets, visual QA, 128 rendered docs, requirement/test inventory, secret scan, and diff checks pass.
