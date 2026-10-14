# Deploy: preflight and plan (2026-10-13)

**Verdict: NOT cleared to deploy. Nothing has been deployed, bought, or configured.** You said to stop before a real deploy.

## Preflight results
| check | result |
| --- | --- |
| API tests (`pytest`) | PASS 16/16 |
| Playwright e2e + axe | PASS 65/65 (`cd apps/web && npm run e2e`), Chrome only |
| Parity must-haves | **FAIL** 8 of 14 done (score 68.2): SSO handoff, docs link target, Redis (untested vs real), Stripe (untested vs real), usage per key/cost, legal review; plus new must: data-handling page (built, but retention not enforced yet) |
| Brand sweep | PASS clean |
| `next build` | PASS (19 routes, Next 16.4.0) |
| `npm audit --omit=dev` / `pip-audit` | PASS 0 / none |
| Secret scan in tracked files | PASS none found |
| Open S1 / S2 bugs | PASS none (S1 0, S2 0; see bugs.md "to check" T1-T6) |
| Terms / Privacy live with processors | **FAIL** draft placeholders, no processor list |
| Favicon, OG image, logo | **FAIL** none yet (logo brief only) |
| Account deletion | PASS built and tested (org delete, leave, account-service webhook); Clerk webhook endpoint still to be created by you |
| Cookie banner | n/a: no cookies set by the app (theme in localStorage only); re-check if analytics added |
| Streaming | known gap (not a must in matrix, but #1 dev expectation) |

## Blockers to clear first (in order)
1. NEXORA SSO handoff: code done (see backend.md). Left: allow `https://gateway.onenexora.com` in Clerk, set `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, run one real sign-in on a preview deploy, change the NEXORA Gateway card CTA.
2. Run against real Postgres (Neon) + Redis (Upstash) + Stripe **test** mode; fix what breaks.
3. ~~Playwright e2e + axe scan~~ done (F07 SSO handoff still needs a real sign-in on a preview).
4. Legal pages reviewed + processors list. (Account deletion and retention purge are built; add the Clerk webhook `/webhooks/account` + `ACCOUNT_WEBHOOK_SECRET`.)
5. Logo/favicon/OG; decide pricing tiers (see launch/pricing.md); real docs at docs.onenexora.com.
6. Trademark/domain screening for "NEXORA" (never run; see brand.md).

## Production plan (you create accounts; I never enter keys)
| part | where | notes |
| --- | --- | --- |
| web `apps/web` | Vercel, root dir `apps/web`, domain `gateway.onenexora.com` | env: `NEXT_PUBLIC_API_BASE=https://api.onenexora.com`; **no** `NEXT_PUBLIC_DEV_AUTH` |
| api `apps/api` | Fly.io or Render from `apps/api/Dockerfile`, domain `api.onenexora.com` | `ENV=prod`, release command `alembic upgrade head`; min 2 instances; the API refuses to boot without `AUTH_JWKS_URL`, `AUTH_ISSUER`, `REDIS_URL` |
| Postgres | Neon, separate **production** project, backups on | `DATABASE_URL=postgresql+asyncpg://...` (verify Alembic on Postgres first) |
| Redis | Upstash | `REDIS_URL` |
| upstream | `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` as host secrets | live keys only in the host |
| CORS | `CORS_ORIGINS=https://gateway.onenexora.com` | remove localhost in prod |
| Provider-key encryption | `CREDENTIAL_ENCRYPTION_KEY` (32 random bytes, base64) as a host secret | required in prod (boot fails without it); store a copy in your password manager: losing it makes saved customer keys unreadable |
| Stripe | live mode: recreate Starter price, webhook `https://api.onenexora.com/webhooks/stripe`, set `STRIPE_*`; one real purchase + refund | API rejects `sk_test_` in prod |

## DNS (at your registrar for onenexora.com; values come from each host's domain screen)
| type | name | value |
| --- | --- | --- |
| CNAME | gateway | `cname.vercel-dns.com` (confirm in Vercel) |
| CNAME | api | the Fly/Render hostname shown after adding the custom domain |
| TXT | as asked | host verification values |
| TXT/CNAME | per provider | SPF + DKIM for Resend when email is added; DMARC `v=DMARC1; p=none; rua=mailto:you@onenexora.com`, tighten later |
Keep `account.onenexora.com` SSO session cookie on `.onenexora.com` if you want shared login; confirm with the account service config.

## Watch (first week)
Error tracking on api and web; uptime checks on `https://api.onenexora.com/v1/health` and the home page; alert on 5xx rate, p95 latency, webhook failures, Redis/DB errors; daily look at quota-429 and 401 spikes; verify the first Stripe webhook arrives and plan changes. Do the core flow live (create key -> call -> log) and have someone repeat it on a phone.

## Ask
When blockers 1-4 are done I'll re-run this preflight; deploy only after you say go.
