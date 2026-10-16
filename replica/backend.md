# Backend status (2026-10-13)

## Done and tested (13 API tests, `pytest`)
- Hashed API keys (sha256, shown once), revoke, rotate (API), per-key rpm limit, last_used.
- `/v1/chat` + OpenAI-compatible `/v1/chat/completions`, JSON error envelope, `x-nexora-request-id`.
- Quota per org per month (429 `quota_exceeded`), rate limit (429 + `Retry-After`).
- Roles (viewer/developer/admin/owner) enforced per route; cross-org access returns empty/404 (tested).
- Control-plane auth: dev headers (dev only) or JWT via JWKS (`AUTH_JWKS_URL`, `AUTH_ISSUER`); prod refuses to boot without them and without `REDIS_URL`.
- Redis sliding-window limiter (same interface as the in-memory one). **Not exercised against a real Redis yet.**
- Stripe Checkout, Billing Portal, webhook (`checkout.session.completed`, `customer.subscription.updated|deleted`, `invoice.payment_failed`): signature verified, event ids stored, idempotent; downgrade on cancel. Tested with signed fake events. **Not exercised against Stripe test mode yet.**
- Alembic initial migration (`apps/api/migrations`), verified `upgrade head` on SQLite. Postgres not yet run.
- `seed.py` for demo data. `.env.example` lists every variable.

## You must provision (I never create accounts or enter keys)
1. **Postgres** (Neon/Supabase): set `DATABASE_URL=postgresql+asyncpg://...`, run `alembic upgrade head`; enable daily backups.
2. **Redis** (Upstash): `REDIS_URL`.
3. **NEXORA account SSO**: BUILT (see SSO section below). Remaining for you: confirm on the Clerk dashboard that `https://gateway.onenexora.com` is an allowed redirect/origin and test one real sign-in.
4. **Stripe (test mode)**: `STRIPE_SECRET_KEY`, create a $19/mo Starter price -> `STRIPE_PRICE_STARTER`, webhook endpoint `/webhooks/stripe` -> `STRIPE_WEBHOOK_SECRET`. Test with card 4242 4242 4242 4242.
5. **Upstream provider key** (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`) for the platform default.
6. **Resend** + sending domain (SPF/DKIM) when email is added.

## Not built yet
policies/DLP/injection, quota emails, webhooks out, invites from inside Gateway (they live in the NEXORA account).

## Security checklist
- [x] secrets only in env vars; `.env*` ignored; `.env.example` has no values; nothing secret in the web bundle (only `NEXT_PUBLIC_API_BASE`, dev flag)
- [x] server-side validation on every route (Pydantic: lengths, enums, ranges)
- [x] authorization on every read/write, tested with a second org
- [~] rate limits: data plane yes; auth/sign-up belong to NEXORA account service; playground limited to 30/min but only per key id, review
- [x] webhook signature verified, idempotent
- [n/a] uploads: none
- [x] no prompts stored; logs hold hash only; request logs carry no key material (old "last 6 chars of key" logging removed)
- [x] dependencies audited: `pip-audit` clean; `npm audit --omit=dev` 0 vulns (Next 16.4.0)
- [ ] privacy policy lists processors (Stripe, host, Neon, Upstash, upstream LLM provider): policy page is still a draft
- [ ] `DEV_AUTH` header trust is disabled when `ENV=prod` (code) but verify in deploy preflight
- [ ] CORS origin list reviewed for the real domain
- [ ] Cancel is one click via Stripe portal (built, untested with Stripe)

## Known gaps worth fixing before launch
- Playground rate-limit key is per member but the limiter is the per-key limiter; fine for now.
- `request_logs` writes happen in the request path (one commit per call). Move to a queue at scale.
- Quota is counted from logs plus rollups (indexed by org_id, ts), and since the review fixes below calls are reserved before dispatch.

## SSO handoff (2026-10-14)
Found by reading the public sign-in page: account.onenexora.com is a **Clerk production instance** (frontend API `clerk.onenexora.com`, issuer `https://clerk.onenexora.com`, JWKS reachable and RS256).
- **Web** (`apps/web/lib/session.tsx`): `@clerk/clerk-react` with the instance's public publishable key only (no secret key in the app). `/app/*` is gated: signed out -> redirect to `account.onenexora.com/sign-in?redirect_url=<current>`, signed in -> every API call carries a fresh Clerk session JWT (`getToken()`), Sign out button in the header. Fails closed when no key is configured (verified in a production-mode build: dashboard shows "Sign-in is not configured", no API calls).
- **API** (`app/deps.py`): verifies RS256 signature via JWKS (cached 1h), issuer, `exp/iat/sub/iss` required, 5s leeway, and `azp` must be one of `CORS_ORIGINS` (a token minted for another site is rejected). Supports Clerk token v1 (`org_id`, `org_role`) and v2 (`o.id`, `o.rol`); no org = personal workspace keyed by `sub`. Org and member are provisioned on first sign-in; first member is `owner`.
- **Tests:** 9 new tests with a locally generated RSA key and a fake JWKS (valid, personal workspace, v2 org, expired, wrong issuer, foreign `azp`, HS256 forgery, dev headers ignored when `DEV_AUTH` off, cross-org isolation). 25 pass.
- Same-domain sessions: gateway.onenexora.com is a subdomain of the account's primary domain, so the account session is shared without Clerk satellite config.
- **Not verified live:** I did not sign in (I never enter credentials), and a production Clerk key does not load on localhost. First real check must happen on a deployed `gateway.onenexora.com` preview.
- Known limits: the default Clerk session token has no email claim (the UI shows the email from Clerk's user object; the API stores an empty email unless you add a custom claim in Clerk); a member's role is set from the account role at first sign-in and afterwards owned by Gateway (changed on the Team page, not re-synced from Clerk); no `/webhooks/account` sync yet (org/member deletion, GDPR purge).

## Streaming (2026-10-14)
- `stream: true` on `/v1/chat`, `/v1/chat/completions` and `/api/playground` returns `text/event-stream` of OpenAI-style `chat.completion.chunk` objects (role chunk, content deltas, a final chunk with `finish_reason` and `usage`, then `data: [DONE]`). Both data-plane routes use this one format.
- Adapters (`stream_chat`) for Anthropic (message_start / content_block_delta / message_delta / error events), OpenAI (`stream_options.include_usage`) and the mock. Upstream refusals are raised **before the first byte**, so callers get a normal JSON error + correct HTTP status; failures after the stream started are sent as an in-band `data: {"error":...}` event and logged as `error`.
- Auth, rate limit and quota run before anything streams (plain JSON 401/429). A streamed call counts toward quota.
- Exactly one log row per stream, written by the stream's own DB session in `finally` (shielded), including when the client disconnects: status **499**, decision `allow` (the call happened and counts), tokens = provider-reported if seen, else an estimate (chars/4). Dashboard shows 499 as "cancelled by client".
- Tests (37 total pass): shape + logging, OpenAI route, preflight errors stay JSON, quota counting, refusal before first byte, mid-stream failure, disconnect (generator closed -> one 499 row), playground, and adapter parsing against canned upstream SSE (Anthropic, OpenAI, HTTP error, in-stream error). Verified over real HTTP with curl (chunks arrive 400 ms apart; a client abort logs 499) and in the browser (playground streams, Stop button works).
- **Not verified against the real Anthropic/OpenAI APIs** (no keys here); parsing follows their documented event formats.
- Not done: tool calls / non-text content blocks are ignored in streams; no heartbeat comments for idle proxies; no cost estimate.

## Usage per key (2026-10-14)
- `GET /api/usage?from=YYYY-MM-DD&to=YYYY-MM-DD&group=key|model|day[&format=csv]`: SQL aggregation (not row loading) of calls, blocked, errors, tokens in/out per key, model or UTC day, plus totals. Default: last 30 days. Range is inclusive, `from <= to`, max 366 days, 422 `invalid_range` otherwise. Org-scoped, viewer+.
- Unattributed calls (playground, or a deleted key) are grouped under "Playground", never dropped, so totals always equal the sum of rows. Revoked keys keep their history and are marked.
- CSV neutralises spreadsheet-formula injection (a key named `=HYPERLINK(...)` is exported as `'=HYPERLINK(...)`).
- Postgres-safety: grouped by label (bind-parameter expressions repeated in GROUP BY are rejected by Postgres) and UTC day bucketing via `timezone('UTC', ts)`; compiled for the Postgres dialect but **not run against a real Postgres**.
- Web (`/app/usage`): By key / By model / By day, date range with 7/30/90-day presets, totals row, daily chart with empty days shown as gaps, CSV download, empty/error/invalid-range states.
- Tests: 7 new (44 total): grouping, inclusive ranges, validation, org isolation, unattributed calls, CSV. Checked in the browser against seeded data.
- Still no cost: token counts only. Usage reads `request_logs` plus the `usage_daily` rollups that retention writes (see Retention and deletion below), so history outlives log retention.

## Retention and deletion (2026-10-14)
**Retention** (`app/retention.py`): free 7 days, starter 30, team 90, enterprise 365. A daily in-process job (and `python -m app.retention` for a cron) rolls whole UTC days older than the window into `usage_daily` (counts per org/day/key/model: no content) and deletes those logs and their security events, one transaction per day. Merge, not replace, if a straggler log arrives for a rolled-up day. A day is therefore in exactly one place, and usage/overview/quota read both (`app/usage.py`). Quota previously counted live logs only, which would have reset the month's usage when logs were purged; it now adds rolled-up billable calls. Effective retention is the window plus up to 24h. Latency p50 on the overview only covers retained logs. Verified: 9 tests, plus a real SQLite run (40 old logs purged, usage totals identical before and after).
**Organization deletion**: `POST /api/org/delete` (owner only, must type the org name exactly): cancels the Stripe subscription first (if Stripe fails, nothing is deleted, 502), then hard-deletes events, logs, usage counts, keys, subscription row, members and the org. Stripe webhook event ids and the Stripe customer record are kept (accounting). `DELETE /api/me` removes the caller's membership; refused for the last member or sole owner. Settings page has retention info and the delete form (verified in the browser: button disabled until the name matches; all tables empty afterwards).
**Account-service sync**: `POST /webhooks/account` verifies Svix signatures (HMAC-SHA256, 5-minute tolerance) with `ACCOUNT_WEBHOOK_SECRET`; handles `user.deleted` (drops memberships, deletes orgs left empty and the personal workspace), `organization.deleted`, `organizationMembership.deleted`; idempotent; refuses all requests when the secret is unset. **You must add the endpoint and secret in the Clerk dashboard (Webhooks)**; not tested against real Clerk, only against locally signed payloads.
Limits: deletes are single statements per org (large orgs would want batching); no data export yet; in-process job runs in every worker (idempotent, wasteful); deletion cannot recall data already sent to your model provider; backups (Neon) keep deleted data until they expire, say so in the privacy policy.

## Provider keys, bring your own (2026-10-14)
- **Model**: `provider_connections` (org, provider anthropic|openai, label, encrypted key, `…last4` hint, default flag, status ok/failing/untested). Partial unique index: at most one default per org. Max 10 per org. Migration included.
- **Encryption** (`app/providers.py`): AES-256-GCM, random nonce per value, ciphertext bound to `connection id + org id` as authenticated data (a copied blob will not decrypt under another row or org). Key from `CREDENTIAL_ENCRYPTION_KEY` (32 bytes base64); the API refuses to boot in prod without it; a fixed dev key is used outside prod. Format byte `0x01` leaves room for key rotation (not implemented).
- **API** (`/api/providers`): list (developer+), add / test / make default / delete (admin+). A key is verified against the provider (`GET /v1/models`) **before** it is stored: rejected -> 422 `provider_rejected_key`, unreachable -> 502, nothing saved either way. Responses never include the key. Verification calls are rate limited (10/min/org) because each makes an outbound request.
- **Data plane**: a call uses the org's connection for the requested `provider` (default first), else the org's default connection, else the shared platform key from env, else (dev) the mock. Streaming and the playground use the same resolution. If the provider answers 401/403 to a saved key, the caller gets a generic `provider_auth_failed` (the provider's message is not passed through because it can echo key fragments) and the connection is flagged "failing" on the dashboard.
- **Deletion**: org deletion and account-service deletions remove stored keys.
- **Deliberately not built**: custom base URLs (Azure OpenAI, proxies): a user-supplied URL makes the server call arbitrary addresses (SSRF) and needs allow-listing and DNS pinning first. Key rotation of `CREDENTIAL_ENCRYPTION_KEY`. Per-key model allow-lists. Fallback between connections.
- **Tests**: 14 API tests (encryption and row binding, no plaintext in the DB, key never returned, verify-before-store, default rules, roles, isolation across orgs, the upstream sees the org's own key and never another org's, streaming, provider auth failure, deletion, key rules) and 3 browser tests (add/reject/test/default/remove, developer read-only, axe). Total 78 API + 69 browser. Not verified against the real Anthropic/OpenAI key-check endpoints.
- **Operational**: back up `CREDENTIAL_ENCRYPTION_KEY` separately from the database; losing it makes every stored provider key unreadable (customers would have to re-enter them).

## Data export (2026-10-15)
- `GET /api/org/export` (admin+): one valid JSON document, **streamed** in pages of 1,000 rows per table (ordered by id), so memory stays flat: a local run with 60,000 logs produced 22 MB in 4.3 s while the API process went from 93 MB to 107 MB, first byte in 5 ms. Sections: organization, members, api_keys, provider_connections, usage_daily, security_events, request_logs, subscription, plus `generated_at` and a plain-language `notes`. Excluded by design: key hashes, encrypted provider credentials, key secrets (not recoverable), prompt text (never stored).
- `GET /api/me/export` (any member): only the caller's own membership record and the org name, never other members' data.
- Rate limited to 3 per minute per org (a full export reads every table); every export is logged (org and member ids only). `Cache-Control: no-store`; filename `nexora-gateway-export-<org id>-<date>.json` (the org id, never the user-chosen name).
- Settings page: "Export your data" card (admins: organization data + own record; developers/viewers: own record only). The data-handling page says data is available on request without a ticket.
- Tests: 6 API tests (everything present, no secrets, valid JSON across page boundaries with 2,503 logs, empty org, role + isolation, own-record only, rate limit) and 2 browser tests. 84 API + 71 browser total.
- Limits: the export covers what Gateway stores; the NEXORA account itself (name, sign-in) and Stripe billing records are held by those services and need their own export. No machine-readable schema file published.

## Team (2026-10-15)
- **Where things live**: invites, and removal from the company, are NEXORA account (Clerk) actions; Gateway cannot invite without a Clerk secret key and does not hold one. Gateway owns each member's *role inside Gateway* and a reversible *suspend* switch (`members.status`, migration included). Roles are set from the account role at first sign-in, then managed on the Team page.
- **API**: `GET /api/members` (viewer+; ids and emails of the org's own members only), `PATCH /api/members/{id}` with `role` and/or `status` (admin+).
- **Rules** (enforced on the server, mirrored in the UI): owners manage everyone; admins manage only developers and viewers and cannot grant admin or owner; nobody changes their own role or access (409); there is always an active owner (hard stop kept even though self-edit rules already guarantee it); other orgs' members are 404; changes are logged (ids only).
- **Suspension**: a suspended member gets 403 `member_suspended` on everything except `GET /api/me` (so the app can say why), `GET /api/me/export` and `DELETE /api/me` (data rights and leaving do not depend on an admin's goodwill). Signing in again does not undo it. The UI replaces the dashboard with an explanation, "Download my data" and "Leave organization".
- **Important limit**: suspension does **not** revoke the organization's API keys (they belong to the org, not a person). The Team page says so and points to key rotation.
- **Why suspend and not remove**: removing a Gateway row would be undone at the person's next sign-in (they are still in the account's organization and would be re-provisioned). Suspension is the Gateway-level control that survives that; true removal is done in the NEXORA account, and the `organizationMembership.deleted` webhook then deletes the row.
- Tests: 9 API tests (rules, isolation, suspension and data rights, validation) and 3 browser tests plus 2 axe scans. 93 API + 75 browser total.

## Review fixes (2026-10-16)
Findings from the PR review and the SonarCloud quality gate, each verified against the code before changing it:
- **Quota can no longer be overshot by concurrent calls.** A call is committed as `pending` before it is sent upstream; requests that run at the same time see each other, and one that would exceed the quota removes its own reservation and gets 429. At the exact boundary two racing calls can both back out (conservative), never both get in. Stale `pending` rows (process died mid-call) are settled as errors after 15 minutes by the retention job. The Pill shows "In progress".
- **Unexpected upstream failures** (a response Gateway cannot parse) are logged as errors with 502 `upstream_invalid_response` and do not count toward quota, on both the normal and the streaming path (in-band error event).
- **Saved provider key unreadable** (corrupted, or `CREDENTIAL_ENCRYPTION_KEY` changed): 502 `provider_credentials_unreadable` telling the user to re-add it, connection flagged failing.
- **Concurrent provider adds**: the database arbitrates the single default (a loser falls back to non-default) and the 10-key cap is re-checked after insert.
- **Stripe webhook** refuses all requests (503) when `STRIPE_WEBHOOK_SECRET` is empty, and production refuses to boot with Stripe enabled but no webhook secret. Before this, an empty secret made forged signatures computable.
- **JWT verification** runs in a worker thread with a 5 s JWKS timeout; PyJWT floor raised to 2.14 (the review cited advisories fixed in 2.12 and 2.14; the lock pins 2.15.1).
- **CSV export** neutralises formulas after leading spaces and for leading newlines.
- **Migration** `unique member per org` now deletes duplicate members first (keeps the oldest row per person) so it cannot fail on data created by the earlier race.
- **Supply chain (Sonar)**: `requirements.lock` / `requirements-dev.lock` are hash-pinned; CI and the Dockerfile install with `--require-hashes --only-binary :all:`; `npm ci --ignore-scripts`; no `npx` in CI; the image runs as a non-root user and copies only `app/`, `migrations/` and `alembic.ini`. Not verified: a real `docker build` (needs a base-image download).
- Web: query value encoded, usage ranges over 366 days stopped client-side, a stream that ends without `[DONE]` is reported as cut off, floating promises awaited, data-handling and landing copy corrected (rejected calls are not in the audit log; member emails are stored when the account provides one).
