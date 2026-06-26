# Security and Policy Model

> **Audience:** operator and maintainers.
> **Status:** ✅ Adjustable policy modes implemented.
> **Default:** `all` — maximum personal recall, no built-in URL policy filtering or daemon redaction; explicit local block rules still apply.

---

## Core boundary

The daemon is local-first and WSL-resident. It assumes captured page text may be private and may contain hostile prompt-injection text. It does **not** assume a multi-user enterprise DLP posture.

| Boundary | Current control |
|---|---|
| Network | Daemon binds to `127.0.0.1` by default. |
| API auth | Bearer token required for memory/admin APIs. |
| Health/UI shell | `/health` and `/ui` are public loopback only; `/ui` HTML includes a same-origin token bootstrap for operator UX, while static assets stay token-free. |
| Durable storage | WSL XDG paths; repo and Chrome profile are not storage roots. |
| Browser bridge | Content scripts message service worker; service worker owns daemon fetch/auth/queues. |
| Agent safety | Captured page text is untrusted evidence, never instructions. |

---

## Policy modes

| Mode | Purpose | Filtering | Redaction | Notes |
|---|---|---:|---:|---|
| `all` | Maximum personal recall. | Built-in URL filters off; explicit local block rules on; DOM skip retained | ❌ Off | Default. |
| `recall` | Broad recall with minimal protective boundaries. | ⚠️ Minimal | ✅ On | Blocks incognito/internal/file/non-web schemes. |
| `balanced` | Practical privacy with less overblocking than strict. | ✅ Moderate | ✅ On | Blocks private hosts, known high-risk domains, and high-risk query keys. |
| `strict` | Legacy broad privacy filtering. | ✅ Broad | ✅ On | Keyword-heavy domain/path/query blocks. |

---

## `all` mode risk acceptance

`all` intentionally stores original URL/title/body text without daemon redaction and without built-in URL/domain/path/query filtering. It still applies explicit local block rules and skips hidden/form/editable/script/style/no-script DOM text because Operator requested those surfaces stay omitted. This is an operator-selected personal recall mode.

Known consequences:

- visible/exposed page secrets can be stored and indexed;
- account, email, chat, health, payment, and local/private pages can be stored;
- only explicit local block rules narrow capture;
- Chrome platform restrictions still apply where extension injection is refused.

Mitigations that remain even in `all`:

- loopback-only daemon bind by default;
- bearer auth for memory/admin APIs;
- runtime data is outside the repo;
- secret scan protects committed repo content;
- forget-by-domain/URL can delete stored memory after the fact.

---

## Non-`all` redaction

In `recall`, `balanced`, and `strict`, redaction runs before DB/FTS/blob storage for:

- private-key blocks;
- bearer-token-shaped strings;
- `api_key` / `secret` / `token` assignment shapes;
- SSN-shaped strings;
- credit-card-like digit runs;
- URL username/password;
- sensitive query values and fragments;
- opaque long path/token segments.

---

## Current controls

- API token required for `/capture`, `/visit-events`, `/media-artifacts/*`, `/search`, `/ready`, `/recent`, `/timeline`, `/documents/{id}`, `/snapshots/{id}`, `/policy/*`, `/doctor`, and `/forget`.
- `/health` exposes minimal daemon status plus `policy_mode`.
- Daily-driver install stores the daemon API token in protected WSL config files and injects it into the Windows-local extension artifact; the token is never committed.
- Token rotation is supported:

  ```bash
  BMD_ROTATE_TOKEN=1 BMD_POLICY_MODE=all ./scripts/install-daily-driver.sh
  ```

- Local web UI is served from loopback at `/ui`; the HTML bootstrap embeds the current daemon token so the dashboard auto-loads without manual paste. Static JS/CSS assets remain token-free, and every memory/admin API call still requires the bearer token.
- Deletion UX requires explicit browser confirmation before UI/popup forget-domain calls, and the daemon returns deletion receipts.

---

## Current limitations

| Limit | Status |
|---|---|
| Native messaging hardening | Not implemented. |
| Semantic embeddings | Not implemented. |
| Encrypted backups | Not implemented. |
| Rich allow/redact/metadata-only rules | Not implemented. |
| Retention/compaction | Not implemented. |
| Cloud processing | Not implemented and should not be added without explicit approval. |
