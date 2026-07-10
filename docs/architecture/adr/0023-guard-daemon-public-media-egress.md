---
id: ADR-0023
status: accepted
date: 2026-07-10
decision_date: 2026-07-10
decider: Operator
scope: repo
supersedes: []
superseded_by: []
related:
  - docs/security-model.md
  - docs/media-artifacts.md
  - daemon/src/browser_memory_daemon/media.py
  - daemon/src/browser_memory_daemon/media_worker.py
verification:
  - BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_media_worker.py
---

# ADR-0023: Guard daemon-public media egress

## Context

The media sidecar architecture keeps text capture independent from media bytes, but the daemon-public worker still fetches public `http:`/`https:` media outside Chrome. That path must not become a general-purpose proxy from authenticated local callers or captured page metadata to private networks.

Before this decision, the daemon fetch path relied on `urllib` defaults. That allowed implicit redirects, did not validate every HLS child request, and could send a full page URL as the `Referer` header.

## Decision

Daemon-public media fetches shall go through one guarded public-fetch path.

The guard:

- permits only `http:` and `https:` URLs for daemon-public network fetches;
- resolves hostnames before every request and rejects loopback, private, link-local, unspecified, multicast, reserved, and otherwise non-global addresses by default;
- disables implicit redirects and validates every redirect target against the same policy with a finite hop budget;
- applies the same policy to HLS master playlists, variant playlists, init maps, and media segments;
- enforces bounded HLS request count, playlist bytes, recursion depth, artifact bytes, and deadline budgets;
- sends no `Referer` header from the daemon-public fetch path;
- keeps browser-credentialed fetches inside Chrome rather than exporting cookies to WSL;
- allows explicit operator/test private-host allowlisting through configuration when a private destination is intentional.

## Decision drivers

- A page-controlled media URL must not make the daemon contact internal infrastructure by default.
- A public URL redirecting to private space must be blocked at the redirect target.
- HLS expansion must not bypass policy by hiding private URLs in child playlists or segments.
- Full captured page URLs can contain sensitive paths/query parameters and should not be leaked as daemon fetch referrers.
- The hardening must preserve the current lazy media model and keep text capture independent from media success.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Disable daemon-public media fetch entirely | Strongest egress reduction | Loses public media backfill and HLS coverage | Rejected |
| Keep `urllib` defaults | Minimal code | Allows implicit redirects and weak egress control | Rejected |
| Guarded stdlib fetch path | Preserves current architecture; centralizes policy; testable with fake resolver/opener | More policy code in `media.py` until Phase 4 extraction | Chosen |
| Browser-only media fetch | Keeps cookies in Chrome | MV3 suspension and no daemon-wide worker/retry lane | Rejected as sole lane |

## Consequences

- Positive: daemon-public media cannot reach private/internal addresses by default, including through redirects and HLS children.
- Positive: no full page URL is emitted as daemon-public `Referer`.
- Positive: tests can prove egress policy with fake resolver/opener and no real network.
- Negative: local/private media fixture fetches now require an explicit private-host allowlist in tests or operator config.
- Neutral: browser credentialed media behavior remains separate and unchanged.

## Verification / validation

- Verification: `daemon/tests/integration/test_media_worker.py` covers DNS-to-private blocking, IPv6 loopback literals, allowlisted private hosts, missing `Referer`, public-to-private redirects, redirect loops, HLS private child URLs, HLS request budgets, and existing loopback fixtures with explicit allowlist.
- Verification: focused command passed: `BMD_PYTHON=/tmp/browser-memory-daemon-verify-venv/bin/python -m pytest -q daemon/tests/integration/test_media_worker.py`.
- Validation: supports HRD-002 / VAL-002 by proving hostile media references cannot make a disallowed daemon-public connection and cannot leak the full page URL as referrer.

## Revisit triggers

- Supersede this ADR if Phase 4 extracts `media_fetch.py` and materially changes the egress guard interface.
- Supersede this ADR before adding proxy support, authenticated daemon fetch, non-HTTP schemes, or broad private-network crawling.
- Revisit allowlist UX if daily-driver media sources require intentional private media backfill.

## References

- `docs/security-model.md`
- `docs/media-artifacts.md`
- `daemon/src/browser_memory_daemon/media.py`
- `daemon/tests/integration/test_media_worker.py`
