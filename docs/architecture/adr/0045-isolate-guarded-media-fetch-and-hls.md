# ADR-0045: Isolate guarded media fetch and bounded HLS transport

- Status: accepted
- Date: 2026-07-10
- Amended: 2026-07-10 after late adversarial transport review
- Decision owners: Browser Memory Daemon maintainers
- Supersedes: ADR-0023
- Related: ADR-0005, ADR-0042, ADR-0044, REQ-027, REQ-036

## Context

ADR-0023 established the guarded daemon-public fetch policy inside `media.py`: HTTP(S)-only network egress, pre-request address validation, redirect revalidation, no `Referer`, explicit private-host allowlisting, and bounded HLS child expansion. The policy passed adversarial fake-resolver/opener tests, but its transport, HLS parser/assembler, artifact facade, and repository code still shared one module.

Phase 4 requires reversible decomposition without weakening the egress guard or changing compatible `browser_memory_daemon.media` imports.

## Decision

1. `media_fetch.py` owns the MIME-safe guarded HTTP/data primitive, hostname/address validation, redirect handling, response-byte limits, per-read deadline enforcement, and response-socket timeout tightening.
2. `media_hls.py` owns HLS request-budget state, bounded playlist parsing, variant selection, init-map/segment expansion, depth/deadline checks, and bounded assembly.
3. Every HLS playlist, variant, map, and segment request continues to call `media_fetch._guarded_public_fetch`; HLS transport does not open network connections independently.
4. The daemon-public path continues to send no `Referer` and no browser cookies. Private destinations remain denied unless their normalized hostname is explicitly allowlisted.
5. `media_transport.py` is the acyclic coordinator. It classifies direct versus HLS responses, creates the aggregate HLS request budget before the first video network open, enforces MIME/path playlist caps and bounded magic-prefix sniffing, and delegates detected playlists to `media_hls.py`. The dependency direction is coordinator → HLS → guarded fetch; `media_fetch.py` never imports HLS.
6. Initial video redirects consume the same aggregate HLS request budget as variant, map, and segment requests. Response-body loops recheck the shared deadline and tighten the underlying response-socket timeout before every read.
7. `media.py` remains the compatibility facade and re-exports coordinator, guarded-fetch, and HLS callables by object identity. Worker behavior, status reasons, endpoint behavior, and configuration remain unchanged.
8. Resolver and opener test seams remain in `media_fetch.py`; HLS clock and asset-fetch seams remain in `media_hls.py`; direct-versus-HLS orchestration tests call `media_transport.py`.

No schema migration, new dependency, egress-policy relaxation, or live-service change is introduced.

## Consequences

### Positive

- Guarded egress policy has one inspectable owner.
- HLS parsing and assembly can evolve independently while every child request remains policy-gated.
- `media.py` becomes materially thinner without a flag-day import change.
- Focused unit and integration tests can patch the module that owns each seam.

### Tradeoffs and deferred work

- DNS resolution and connection establishment still use the accepted ADR-0023 stdlib behavior; this extraction does not introduce proxying or socket pinning.
- ADR-0047 subsequently replaced bounded whole-artifact buffering with streamed assembly and process-global in-flight request/byte budgets under REQ-036.
- Historical normalizers and explicit requeue remain Phase 4.4 work.

## Verification

- `daemon/tests/unit/test_media_fetch.py` verifies compatibility-facade identities for guarded fetch.
- `daemon/tests/unit/test_media_hls.py` verifies compatibility-facade identities for HLS transport.
- `daemon/tests/integration/test_media_worker.py` verifies private-address denial, allowlist behavior, absent `Referer`, redirect revalidation/loops, HLS child revalidation, total request budget, shared deadline, and assembled fixture storage.
- The same integration module verifies that initial redirects consume the HLS total-request budget, slow-drip body reads cannot exceed the shared deadline, and disguised playlists consume at most the playlist cap plus one detection byte.
- Focused media-worker, Ruff, Mypy, generated-document, architecture, broad repository, concurrency, performance, and isolated cached-Chrome gates are recorded with the implementing commit.
