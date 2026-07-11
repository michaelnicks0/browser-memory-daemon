# ADR-0053: Introduce explicit HTTP route descriptors behind compatible endpoints

- Status: accepted
- Date: 2026-07-10
- Decision owners: Browser Memory Daemon maintainers
- Related: ADR-0012, ADR-0015, ADR-0020

## Context

The standard-library HTTP adapter historically recognized every API path through repeated string comparisons inside `app.py`. Before extracting typed errors or application use cases, the existing method/path precedence, parameter decoding, auth boundary, and error behavior need one inspectable source and executable characterization.

## Decision

1. Keep `BaseHTTPRequestHandler`, `ThreadingHTTPServer`, all endpoint paths, status codes, response bodies, and auth ordering compatible.
2. Define the current API method/path catalog in `routes.py` using immutable descriptors and deterministic first-match precedence.
3. Use route names and extracted parameters from those descriptors inside the existing handler branches; do not move use-case behavior in this slice.
4. Keep UI asset resolution separate because it is a finite static-file concern rather than an authenticated API route.
5. Characterize every API descriptor, dynamic parameter decode, static-before-parameter precedence, authenticated-route rejection, unknown-route behavior, unsupported-method behavior, and `/ready` shape before typed error changes.

## Consequences

- Endpoint discovery and matching no longer depend on scattered path literals.
- The media queue-status static route remains ahead of the general media-artifact parameter route.
- Existing unauthenticated requests are still rejected before request-body parsing or route execution.
- `routes.py` is deliberately small and is not a web framework, dependency-injection layer, or application dispatcher.
- Typed errors, request IDs, structured logging, common security headers, and application extraction remain follow-on Phase 6 work.
