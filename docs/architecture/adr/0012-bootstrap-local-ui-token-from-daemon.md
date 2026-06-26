---
id: ADR-0012
status: accepted
date: 2026-06-26
decision_date: 2026-06-26
decider: Operator
scope: repo
backfilled: false
supersedes: []
superseded_by: []
related:
  - daemon/src/browser_memory_daemon/app.py
  - ui/index.html
  - ui/app.js
  - docs/api.md
  - docs/security-model.md
verification:
  - uv run --with pytest python -m pytest -q
  - node static UI bootstrap check
  - BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
  - live curl smoke for /ui, /ui/app.js, /recent, /timeline, /doctor, /policy/rules
  - ./scripts/secret-scan.sh
  - git diff --check -- .
---

# ADR-0012: Bootstrap the Local UI Token from the Daemon

## Context

The Browser Memory dashboard is served by the daemon at `http://127.0.0.1:8765/ui`. Before this decision, the HTML/JS loaded as public loopback assets, but the dashboard remained mostly useless until the operator manually pasted the bearer token into browser `localStorage`.

That manual paste is bad daily-driver UX. The daemon already knows the token, the UI is same-origin with the tokened memory/admin APIs, and the daemon is bound to loopback by default. Memory/admin APIs should still require bearer auth; the dashboard should simply receive the token from the local daemon when opened from the local machine.

## Decision

We will inject a small inline JSON bootstrap into the served `/ui` HTML containing the current daemon token, policy mode, and storage root. Static `/ui/*.js` and `/ui/*.css` assets remain token-free.

The dashboard JavaScript will prefer the daemon-provided token over any browser-local override, prepopulate the token input, and immediately load recent captures, today's timeline, policy rules, and diagnostics. The existing save button remains as a development/test override, not the normal daily-driver path.

## Decision drivers

- Daily-driver dashboard should be useful on first click.
- Memory/admin API endpoints should continue requiring bearer auth.
- The token should not be committed or written into static UI assets.
- Same-origin loopback HTML bootstrap is simpler and less brittle than asking the extension or the operator to populate dashboard state.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep manual token paste | Strongest separation between UI shell and token | Dashboard is useless until configured; bad operator UX | Rejected |
| Store token only in browser `localStorage` | Survives refresh once configured | Still requires paste or fragile extension-side setup | Rejected as default |
| Add unauthenticated memory APIs for `/ui` only | Zero token handling in UI | Weakens API boundary and complicates auth rules | Rejected |
| Inject same-origin token bootstrap into `/ui` HTML | Opens populated while preserving bearer auth for APIs; token-free static assets | Any local process that can fetch `/ui` can read the token, consistent with local-loopback operator model | Chosen |

## Consequences

- Positive: opening `/ui` from the local daemon immediately renders useful dashboard data.
- Positive: `/recent`, `/timeline`, `/doctor`, `/policy/*`, deletion, media, and detail APIs still require the bearer auth header.
- Positive: static JS/CSS assets stay token-free and safe to diff/cache as code artifacts.
- Negative: `/ui` HTML now carries the token to local loopback clients; this is acceptable only while the daemon remains bound to loopback by default.
- Neutral: the UI save button remains as an override for tests or unusual dev setups.

## Verification / validation

- Verification: `uv run --with pytest python -m pytest -q` covers `/ui` bootstrap injection, token-free static JS, unauthenticated `/recent` rejection, and existing admin APIs.
- Verification: static Node check verifies live/source UI markers and bootstrap consumption.
- Verification: daily-driver install and live curl smoke verify the deployed service serves token-bootstrapped `/ui` while memory APIs still reject requests without the token.
- Validation: the dashboard no longer shows “Add token, then refresh” for normal daily-driver use; it auto-loads recent captures, today's timeline, policy rules, and diagnostics.

## Revisit triggers

- Supersede this ADR before binding the daemon beyond loopback or exposing it through a remote tunnel.
- Supersede this ADR if the dashboard gains a stronger same-origin session mechanism that avoids placing the bearer token in HTML.
- Supersede this ADR if multi-user host support becomes a requirement.

## References

- `daemon/src/browser_memory_daemon/app.py`
- `ui/index.html`
- `ui/app.js`
- `docs/api.md`
- `docs/security-model.md`
