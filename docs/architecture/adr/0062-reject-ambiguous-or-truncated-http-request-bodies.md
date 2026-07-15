---
id: ADR-0062
status: accepted
date: 2026-07-14
decider: Michael
scope: repo
backfilled: true
supersedes: []
superseded_by: []
related: [ADR-0047, ADR-0053, ADR-0054, ADR-0055, ADR-0056, REQ-040]
verification:
  - daemon/tests/e2e/test_http_api.py::test_http_raw_media_upload_requires_explicit_decimal_content_length
  - daemon/tests/e2e/test_http_api.py::test_http_json_body_rejects_ambiguous_invalid_and_truncated_content_lengths
  - daemon/tests/integration/test_ingest_search_forget.py::test_raw_blob_upload_streams_without_whole_artifact_spool_and_rejects_truncated_body
---

# ADR-0062: Reject ambiguous or truncated HTTP request bodies before application use cases

## Context

Browser Memory Daemon uses Python's standard-library HTTP server on an authenticated loopback boundary. Route descriptors, typed errors, request envelopes, and request-independent application use cases already make method/path and failure behavior explicit, but body framing remained an implicit transport concern.

`Content-Length` is security- and integrity-relevant even on loopback. Duplicate, signed, non-ASCII, oversized, or truncated lengths can make an adapter and caller disagree about message boundaries, consume unbounded memory, or pass partial JSON/blob evidence into a domain mutation. Raw uploads also need a known byte budget before streaming starts.

Commit `5161aa8a` implemented strict framing and executable negative cases. This ADR records that durable transport contract without changing the established route, error, telemetry, or application-layer decisions.

## Decision

1. A request may supply at most one `Content-Length` value. When present, it must be a non-empty ASCII unsigned-decimal integer with a bounded header representation.
2. Ordinary JSON requests are bounded by the configured JSON payload limit; the compatibility base64 media route uses its separately configured media payload limit.
3. The HTTP adapter reads exactly the declared JSON length and rejects a short/truncated body before invoking an application use case.
4. Raw media upload requires an explicit valid length before streaming and enforces artifact plus process request/byte budgets without buffering the whole artifact.
5. Duplicate, signed, malformed, oversized, missing-required, or truncated framing is a typed client validation error. It must not be reclassified as an internal failure or expose exception prose.
6. This is an HTTP transport invariant. Application use cases remain request-type independent and do not parse framing headers.

## Decision drivers

- Mutation-owning code must never receive partial or ambiguously framed evidence.
- Raw streaming requires a known upper bound before resource admission.
- Compatible typed errors and redaction-safe telemetry must cover framing failures.
- The loopback boundary should fail closed without adding a new HTTP dependency or server stack.

## Alternatives considered

| Option | Verdict | Reason |
|---|---|---|
| Trust `BaseHTTPRequestHandler`'s first parsed value | Rejected | Duplicate or malformed framing would remain adapter-dependent and ambiguous. |
| Read JSON until EOF | Rejected | Persistent HTTP connections and body-size bounds require an explicit message boundary. |
| Buffer raw uploads before validation | Rejected | Violates the bounded-streaming and process-budget decisions in ADR-0047. |
| Replace the standard-library server | Rejected | Strict framing is small and testable within the existing transport boundary. |

## Consequences

- Positive: application use cases receive only complete, bounded JSON payloads.
- Positive: raw uploads reserve against an explicit size and remain streaming.
- Positive: malformed framing has stable client-visible validation behavior and redaction-safe telemetry.
- Negative: clients that omit raw-upload length or send duplicate/signed values are rejected even if a permissive server might have accepted them.
- Neutral: this decision does not change authentication, route precedence, payload schemas, or domain semantics.

## Verification

- `test_http_raw_media_upload_requires_explicit_decimal_content_length` covers missing and signed raw-upload lengths.
- `test_http_json_body_rejects_ambiguous_invalid_and_truncated_content_lengths` covers duplicate, signed, malformed, and short JSON bodies over a real socket.
- `test_raw_blob_upload_streams_without_whole_artifact_spool_and_rejects_truncated_body` proves raw upload rejects incomplete bytes without weakening the streaming boundary.
- The fast quality gate, generated requirement traceability, secret scan, and documentation drift checks must remain green.

## Related decisions

- [ADR-0047](0047-stream-media-with-process-budgets-and-durable-cache-reservations.md)
- [ADR-0053](0053-introduce-compatible-http-route-descriptors.md)
- [ADR-0054](0054-use-typed-compatible-http-errors.md)
- [ADR-0055](0055-add-redaction-safe-http-request-envelope.md)
- [ADR-0056](0056-separate-http-transport-from-application-use-cases.md)
