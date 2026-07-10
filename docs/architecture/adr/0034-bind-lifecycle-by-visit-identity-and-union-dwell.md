---
status: accepted
date: 2026-07-10
decision-makers: [Michael]
consulted: [TARS]
informed: []
---

# ADR-0034: Bind lifecycle events by claimed visit identity and derive dwell from interval unions

## Context and problem statement

Lifecycle events could previously fall back from an unknown caller-supplied `visit_id` to the latest visit with the same normalized URL. Concurrent tabs and delayed captures could therefore attach telemetry to the wrong navigation. Dwell was incremented from reported `active_seconds` values and only suppressed overlaps with equal starts, so partial overlap, containment, adjacency, and out-of-order delivery could double count.

The capture model requires one visit per navigation/session, durable handling of events that arrive before capture, and dwell based on valid time intervals.

## Decision drivers

- Preserve concurrent same-URL tab identity.
- Accept lifecycle events before or after their matching capture.
- Avoid speculative URL-based attachment for versioned clients.
- Make event retries idempotent and dwell independent of arrival order.
- Keep legacy payloads that omit visit identity readable during the compatibility period.
- Use additive, reversible schema evolution.

## Decision

### Claimed and resolved visit identity

Migration version 7 adds `claimed_visit_id` and `attachment_method` to `visit_events`.

- A payload with `visit_id` is resolved only when exact visit ID and normalized observed URL agree.
- If that visit does not yet exist, the event is stored with `visit_id = NULL`, its `claimed_visit_id`, and `attachment_method = unmatched`.
- Capture ingestion reconciles pending rows only when both claimed visit ID and normalized observed URL match; reconciled rows use `visit-id-delayed`.
- A payload that omits visit identity may use the existing latest-URL lookup during the legacy compatibility window and is marked `legacy-url-fallback`.
- Historical linked rows are backfilled with their existing `visit_id` as the claim and marked `historical`.

The API returns resolved and claimed IDs separately. It never reports an unmatched claimed ID as though it were a resolved visit.

### Interval validation and dwell

New positive-active lifecycle events must include timezone-qualified start and end timestamps. The end must be after the start, the interval is bounded to one day, and reported `active_seconds` must agree with interval duration within one second.

For each resolved visit, dwell is recomputed from all valid positive-active intervals:

1. sort intervals by start time;
2. merge overlap, containment, and adjacency;
3. sum merged durations;
4. replace `visits.dwell_seconds` with the derived total.

Arrival order and duplicate event delivery therefore do not change the result. Historical naive timestamps remain readable as UTC during recomputation, but new interval payloads require an explicit timezone.

## Compatibility and rollback

The migration is additive. Prior binaries ignore appended columns. Rollback remains the prior application plus the pre-migration online backup; there is no destructive down-migration.

The URL fallback remains only for payloads with no visit identity. Phase 2 extension changes make current browser payloads always identity-bearing, after which the fallback is legacy-only evidence rather than the normal path.

## Consequences

### Positive

- Concurrent tabs at the same URL cannot steal one another's identity-bearing lifecycle events.
- Delayed capture reconciles pending events without URL recency guesses.
- Dwell is monotonic with evidence and invariant to overlap or delivery order.
- Attachment quality is visible in SQLite and authenticated detail reads.

### Negative

- Dwell recomputation reads all positive intervals for one visit after each accepted active segment. Visit event volumes are bounded and indexed; future optimization must preserve exact union semantics.
- Legacy no-ID events retain explicit URL fallback until compatibility evidence permits removal.
- Invalid historical intervals remain stored but are excluded from union accounting.

## Rejected alternatives

- **Fallback from an unknown claimed ID to latest URL:** fails concurrent-tab identity.
- **Increment dwell by each report:** double counts overlap and is order-dependent.
- **Deduplicate equal starts only:** misses partial overlap, containment, and bridging intervals.
- **Create placeholder visits before capture:** would invent document/visit authority before accepted text capture.

## Validation

- `daemon/tests/integration/test_visit_lifecycle.py::test_lifecycle_dwell_uses_interval_union_for_overlap_containment_adjacency_and_out_of_order`
- `daemon/tests/integration/test_visit_lifecycle.py::test_claimed_visit_identity_does_not_fall_back_by_url_and_reconciles_after_delayed_capture`
- `daemon/tests/integration/test_visit_lifecycle.py::test_visit_lifecycle_event_validates_ranges`
- `daemon/tests/integration/test_migrations.py::test_version_seven_preserves_claimed_visit_identity_for_historical_events`
- HTTP lifecycle characterization remains covered by `daemon/tests/e2e/test_http_api.py`.
