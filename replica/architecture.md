# Architecture: NEXORA Gateway (standalone product)

## 1. Shape
Two deployables, one database. No microservices.
- **gateway-api** (FastAPI, this repo's `app/`): data plane `/v1/*` (key auth) and control plane `/api/*` (dashboard, session JWT auth). Hosted on Fly.io/Render (long-lived streaming connections; not serverless).
- **gateway-web** (Next.js App Router + TS + Tailwind): marketing site (S01-S06) and dashboard `/app/*` (S10-S22). Hosted on Vercel at `gateway.onenexora.com`.
- **Postgres** (Neon or Supabase) + **Redis** (Upstash) for rate limits, quota counters, short key cache.
- NEXORA main site keeps only a Gateway product card whose CTA goes to `https://gateway.onenexora.com`.

```
Client app --Bearer nx_live_--> api.onenexora.com/v1/chat  (gateway-api)
Browser --> gateway.onenexora.com (Next.js) --session JWT--> gateway-api /api/*
                                  \-- account.onenexora.com (shared SSO)
gateway-api --> Postgres, Redis, Anthropic/OpenAI/Azure OpenAI, Stripe, Resend
```

## 2. Stack
| layer | choice | why |
| --- | --- | --- |
| API | FastAPI + httpx (existing) | repo base; async streaming proxy |
| web | Next.js 15 App Router, TS | marketing SSR/SEO + dashboard in one app |
| styling | Tailwind + tokens from replica-design | consistent, themeable (brand step) |
| DB | Postgres (Neon) | one DB, branching for previews |
| data access | SQLAlchemy 2 async + Alembic | native to FastAPI; migrations = `schema.sql` as 0001 |
| cache/limits | Redis (Upstash) | shared sliding window across workers |
| auth (humans) | existing NEXORA account SSO (Clerk-style); API verifies JWT via JWKS | single login across products; do not build auth |
| auth (machines) | `nx_live_` keys, sha256 at rest, constant-time compare | prefix lookup + hash |
| payments | Stripe Checkout + Billing Portal; test mode until deploy | plans already live: Free/Starter |
| email | Resend | invites, quota alerts |
| jobs | in-process APScheduler -> Fly cron machine later | rollups, retention, quota reset |
| secrets | AES-GCM envelope w/ key from env/KMS | provider creds |
| observability | structlog JSON + OpenTelemetry + `/metrics` | audit + ops |
| hosting | Vercel (web), Fly.io (api) | managed, cheap at 0 users |

## 3. Schema
See [schema.sql](schema.sql): **11 tables** (organizations, members, api_keys, provider_connections, policies, request_logs, security_events, usage_daily, subscriptions, stripe_events, webhooks). Key decisions:
- Isolation: every query scoped by `org_id` from verified identity (data-layer dependency) **plus** RLS via `set local app.org_id`.
- Raw prompts never stored by default; only `prompt_hash`. Optional per-org "store excerpts" for security events, redacted.
- Keys: only `key_hash` + `prefix` + `last4`; secret shown once.
- `provider_connections.is_default` partial unique index: exactly one default per org.
- Money in integer micros. Logs `on delete cascade` with org; key delete keeps logs (`set null`).
- Hard constraint: quota races handled in Redis with atomic `INCR` per org/month, reconciled to `usage_daily` hourly.

## 4. API
### Data plane (key auth)
| route | does | who | in | out | flow |
| --- | --- | --- | --- | --- | --- |
| POST /v1/chat | native chat (Anthropic-shaped), optional `stream` | API key | `{model?, messages[], max_tokens?, temperature?, stream?}` | message + usage + `x-nexora-request-id` | F08 |
| POST /v1/chat/completions | OpenAI-compatible alias | API key | OpenAI body | OpenAI body | F08 |
| GET /v1/models | models allowed for this org | API key | - | list | F03 |
| GET /v1/health | liveness | public | - | `{status}` | - |
Pipeline per call: key lookup -> rate limit (Redis) -> quota -> policy load (cached 30s) -> DLP -> injection -> risk -> route -> upstream -> meter -> async log write. Error envelope: `{"error":{"code","message","request_id"}}`; codes 401/403/429(quota|rate, `Retry-After`)/422/502.

### Control plane (session JWT, org from claim; role-checked)
| route | does | role | flow |
| --- | --- | --- | --- |
| GET /api/overview | KPIs, series, recent events | viewer+ | F01,F04 |
| GET/POST /api/keys, POST /api/keys/{id}/revoke, POST /api/keys/{id}/rotate | key mgmt | developer+ (revoke admin+) | F01,F05 |
| GET /api/logs, GET /api/logs/{id} | audit trail, filters, cursor pagination, CSV export | viewer+ | F04 |
| GET /api/usage?from&to&group | usage/cost | viewer+ | F02 |
| GET/POST/DELETE /api/providers, POST /api/providers/{id}/test | upstream creds | admin+ | F03 |
| GET/PUT /api/policies/{type}, POST /api/policies/{type}/dry-run | policies | admin+ | F04 |
| GET /api/security-events | event feed | viewer+ | F04 |
| GET/POST/PATCH/DELETE /api/members, POST /api/invites | team | admin+ | F06 |
| POST /api/billing/checkout, POST /api/billing/portal, GET /api/billing | billing | owner/admin | F02 |
| POST /api/playground | call through own org with session (no key) | developer+ | F01 |
| GET/PUT /api/settings, webhooks CRUD | org settings | admin+ | - |
### Webhooks in
- `POST /webhooks/stripe` (signature verify, `stripe_events` idempotency) -> update `subscriptions`, `organizations.plan/quota`.
- `POST /webhooks/account` (NEXORA account events: org/member created/deleted) -> sync `organizations`, `members`; deletion = GDPR purge.
### Jobs
rollup logs -> `usage_daily` (hourly); monthly quota reset (1st, UTC); retention purge (daily; Free 7d, Starter 30d); quota 80%/100% email; provider health probe (5 min).

## 5. NEXORA handoff (F07)
Gateway web is a satellite of the shared account: unauthenticated `/app` -> redirect to `account.onenexora.com/sign-in?redirect_url=...`; return with shared session cookie (parent domain `.onenexora.com`) or Clerk satellite-domain config. First visit with no org -> auto-provision `organizations` row from the account org claim and show S21 onboarding. NEXORA site change: Gateway card CTA -> gateway.onenexora.com.

## 6. Parts that bite
- **Streaming metering:** count tokens from upstream `usage` in final SSE event; on client disconnect still bill what was emitted; log in `finally`.
- **Rate limit correctness:** Redis sliding window (sorted set or token bucket Lua); fail-open vs fail-closed on Redis outage = fail-closed for quota, fail-open for rpm, logged.
- **Idempotency:** Stripe events by event id; invite accept; key rotate.
- **Log write path:** must not add latency or lose data: bounded async queue -> batch insert; spill to disk on DB outage.
- **DLP/injection false positives:** ship in `monitor` mode default; `enforce` opt-in; dry-run on past logs impossible without raw prompts, so dry-run on pasted samples.
- **Secrets hygiene:** never log keys/prompts/provider creds; redact in error bodies from upstream.
- **Multi-tenancy:** RLS + scoped queries + tests that assert cross-org access is 404.
- **Time zones:** store UTC; dashboard formats in browser tz; quota boundaries UTC.
- **GDPR:** org delete cascades; member data export; prompt-hash only reduces exposure.
- **Cost accuracy:** model price table versioned in DB/config; cost is an estimate, labelled so.
- **CORS/CSRF:** control plane only from gateway.onenexora.com; JWT in header, not cookie, for API.

## 7. Build order
1. **Vertical slice (M1):** fix repo (imports, `__init__`, delete dead configs) -> Postgres + Alembic 0001 -> hashed keys -> `/v1/chat` w/ Anthropic upstream -> log row -> Next.js shell with SSO redirect -> S11 create key, S14 list logs. Proves F01 end-to-end.
2. **Must (M2):** S10 overview, S12 playground, S13 usage, S19 billing + Stripe test, streaming, error envelope, Redis limits/quota, S01-S03 + S06 marketing, onboarding S21, docs link.
3. **Should (M3):** multi-provider routing + S15, OpenAI-compatible route, S16 model allowlist, DLP + injection (monitor), S17, S18 RBAC, S05 status.
4. **Could (M4):** risk score, webhooks/SIEM export, enforce modes.
5. **Fixes (M5):** from replica-entrepreneur.

Milestone mapping:
| M | screens | tables | routes |
| --- | --- | --- | --- |
| 1 | S11,S14,S07 | organizations,members,api_keys,request_logs | /v1/chat,/v1/health,/api/keys,/api/logs |
| 2 | S01-S03,S06,S10,S12,S13,S19,S21,S22 | usage_daily,subscriptions,stripe_events | /api/overview,/api/usage,/api/playground,/api/billing/*,/webhooks/stripe |
| 3 | S05,S15-S18 | provider_connections,policies,security_events | /api/providers,/api/policies,/api/security-events,/api/members,/v1/models |
| 4 | S20 | webhooks | /api/settings,webhooks |

## 8. Target repo layout
```
/ (repo root)
  apps/api/   app/{main,config,deps,auth,errors}.py, routers/{data,control,webhooks}.py,
              services/{pipeline,ratelimit,metering,dlp,injection,billing}.py,
              adapters/{base,anthropic,openai,azure}.py, db/{models,session}.py, alembic/, tests/
  apps/web/   Next.js (app/(marketing), app/app/(dashboard))
  replica/    recon, architecture, schema.sql, design
  docs/legacy/ old Kong/K8s/ai_config files
```
Move current `app/` -> `apps/api/app/`.
