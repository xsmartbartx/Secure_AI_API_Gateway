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
Streaming (SSE), per-org provider vault, policies/DLP/injection, usage rollups, retention purge job, quota emails, team/invites, webhooks out, account deletion (GDPR purge) endpoint, `usage_daily` rollup (queries read logs directly: fine until ~1M rows/org).

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
