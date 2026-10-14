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
per-org provider vault, policies/DLP/injection, usage rollups, retention purge job, quota emails, team/invites, webhooks out, account deletion (GDPR purge) endpoint, `usage_daily` rollup (queries read logs directly: fine until ~1M rows/org).

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
- Quota check counts logs per call (indexed by org_id, ts). OK for MVP; use a Redis counter later.

## SSO handoff (2026-10-14)
Found by reading the public sign-in page: account.onenexora.com is a **Clerk production instance** (frontend API `clerk.onenexora.com`, issuer `https://clerk.onenexora.com`, JWKS reachable and RS256).
- **Web** (`apps/web/lib/session.tsx`): `@clerk/clerk-react` with the instance's public publishable key only (no secret key in the app). `/app/*` is gated: signed out -> redirect to `account.onenexora.com/sign-in?redirect_url=<current>`, signed in -> every API call carries a fresh Clerk session JWT (`getToken()`), Sign out button in the header. Fails closed when no key is configured (verified in a production-mode build: dashboard shows "Sign-in is not configured", no API calls).
- **API** (`app/deps.py`): verifies RS256 signature via JWKS (cached 1h), issuer, `exp/iat/sub/iss` required, 5s leeway, and `azp` must be one of `CORS_ORIGINS` (a token minted for another site is rejected). Supports Clerk token v1 (`org_id`, `org_role`) and v2 (`o.id`, `o.rol`); no org = personal workspace keyed by `sub`. Org and member are provisioned on first sign-in; first member is `owner`.
- **Tests:** 9 new tests with a locally generated RSA key and a fake JWKS (valid, personal workspace, v2 org, expired, wrong issuer, foreign `azp`, HS256 forgery, dev headers ignored when `DEV_AUTH` off, cross-org isolation). 25 pass.
- Same-domain sessions: gateway.onenexora.com is a subdomain of the account's primary domain, so the account session is shared without Clerk satellite config.
- **Not verified live:** I did not sign in (I never enter credentials), and a production Clerk key does not load on localhost. First real check must happen on a deployed `gateway.onenexora.com` preview.
- Known limits: the default Clerk session token has no email claim (the UI shows the email from Clerk's user object; the API stores an empty email unless you add a custom claim in Clerk); a member's role is set at first sign-in and is not re-synced when changed in Clerk; no `/webhooks/account` sync yet (org/member deletion, GDPR purge).

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
- Still no cost: token counts only. Reads live from `request_logs`; add the `usage_daily` rollup when an org passes ~1M rows.
