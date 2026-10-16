# Recon: Secure AI API Gateway as a standalone product (own site + client dashboard)

Date: 2026-10-13. Own product, own platform (NEXORA), so this is a product recon, not a clone.
Reference inspiration (patterns only, nothing copied): Azure portal / Azure API Management, Apple (marketing restraint).

## 1. Scope
- **App/platform:** Web. Marketing site + authenticated client dashboard + public API.
- **Slice:** Core loop = a customer signs up, creates an API key, sends a governed AI call, sees it in logs/usage, hits a limit or policy block, upgrades.
- **For whom:** Sold product under NEXORA; teams (security / AI / platform engineers) that must put one governed door in front of model calls.
- **Decision:** Gateway leaves the NEXORA main site. NEXORA keeps a product card and "Open Gateway" redirect; Gateway gets its own site (marketing + docs entry + dashboard) on its own subdomain/domain.

## 2. Sources
| source | URL | gives |
| --- | --- | --- |
| NEXORA home | https://onenexora.com | positioning ("Build. Secure. Operate."), 5 products all Beta, shared platform claim, tone: plain, candid |
| Gateway product page | https://onenexora.com/products/gateway | "governed front door", Free $0/100 calls, Starter from $19/1,500 calls, roadmap honesty |
| Gateway landing | https://gateway.onenexora.com | Key. Call. Govern. flow, `/v1/chat`, "Open Gateway" -> `/app` |
| Docs | https://docs.onenexora.com/products | `POST /v1/chat`, `Bearer nx_live_...`, Anthropic-style messages, playground at /app |
| API host | https://api.onenexora.com | `GET /v1/health`, JSON only |
| Console | https://console.onenexora.com | redirects to account.onenexora.com/sign-in (Clerk-style hosted auth); not inspected past login |
| Repo | this repo | FastAPI prototype, see section 7 |
| Architecture doc | Secure_AI_API_Gateway_Architecture.md | target vision: IAM, OPA, risk score, DLP, audit, SIEM, multi-tenant SaaS |
| ChatGPT share | https://chatgpt.com/share/6acdf78d-... | **Not readable** (fetch returned only the title "Analiza repo Secure_AI_API_Gateway"). Paste the text to include it. |
| Azure API Management / Azure portal | learn.microsoft.com, portal.azure.com | IA patterns: resource blade, left nav, metrics, keys, policies. Not yet browsed; do in design step. |

## 3. Current state: findings
**Live (NEXORA):** Gateway is one product among five on a shared account/console/billing. Live gateway proxies to ONE configurable upstream, auth + rate limit + entitlement check + audit log. Multi-provider routing and policy engine are explicitly roadmap.
**Repo prototype:** FastAPI, Bearer static keys from env, in-memory sliding-window rate limit (60/min, per key, lost on restart, not multi-worker safe), OpenAI + Anthropic adapters, unified schema. No streaming, no DB, no usage/cost tracking, no tenants, no DLP/injection/risk, no tests.
**Repo defects to fix before building on it:**
1. `app/main.py` imports `app.adapters.anthropic_adapter` but file is `anthropic_adapters.py` -> app won't start.
2. No `__init__.py` files (README says they exist).
3. `src/main.yml` contains an unresolved git merge conflict and invalid JSON/YAML; `gateway/config.yml` and `config/ai_config.py` (imports nonexistent `deepseek`, Polish path placeholder) are dead. Remove or move to `docs/legacy/`.
4. Keys compared with `in` (not constant-time), plaintext, env-only, no hashing/rotation. Logs last 6 chars of key.
5. README curl has markdown-link-wrapped URL; `.env.example` ships `sk_gateway_prod_secret_key_456` lookalike.
6. Prod and live API contract differ: repo `POST /v1/chat/completions` with `provider` field; live `POST /v1/chat` with Anthropic-shaped body and `nx_live_` keys. Must unify (recommend: keep `/v1/chat` as the native route, add `/v1/chat/completions` OpenAI-compatible alias).
7. Middleware returns plain-text errors; need a JSON error envelope.

## 4. Screen inventory
Marketing site (gateway.onenexora.com or new domain):
| ID | screen | route | purpose | key components | states |
| --- | --- | --- | --- | --- | --- |
| S01 | Home | / | pitch, 3-step flow, CTA | hero, flow diagram, code sample tabs, trust strip | default, mobile |
| S02 | Features / Security | /security | DLP, injection, audit, policy | feature grid, threat diagram | default |
| S03 | Pricing | /pricing | plans, calculator | plan cards, comparison table, FAQ | monthly/annual |
| S04 | Docs landing | /docs (-> docs.onenexora.com) | quickstart, API ref | search, nav, code blocks | default |
| S05 | Status | /status | uptime | status pills | ok, degraded |
| S06 | Legal | /terms /privacy /dpa | legal | prose | default |
| S07 | Sign in / up | account SSO redirect | auth | hosted auth | error, MFA |
Dashboard (gateway app, Azure-portal-like shell):
| ID | screen | route | purpose | key components | states |
| --- | --- | --- | --- | --- | --- |
| S10 | Overview | /app | health at a glance | KPI tiles, requests chart, blocked chart, recent events | empty (no calls), loading, filled, error |
| S11 | API keys | /app/keys | create/revoke/rotate | table, create modal, reveal-once secret | empty, created, revoked, limit reached |
| S12 | Playground | /app/playground | test a call | model picker, messages editor, response pane, risk panel | idle, streaming, blocked, error |
| S13 | Usage & cost | /app/usage | calls, tokens, spend per key/model | date range, charts, table, export | empty, quota near/over |
| S14 | Request logs | /app/logs | audit trail | filters, table, detail drawer (prompt hash, decision, latency) | empty, filtered, no-match |
| S15 | Providers | /app/providers | upstream creds + routing | provider cards, key vault form, test connection | none, ok, failing |
| S16 | Policies | /app/policies | rate limits, model allowlist, DLP rules, injection mode | rule list, editor, dry-run | default, draft, conflict |
| S17 | Security events | /app/security | blocked/flagged prompts | event feed, severity filter | empty, filled |
| S18 | Team & roles | /app/team | members, RBAC | member table, invite modal | owner-only, invited |
| S19 | Billing | /app/billing | plan, invoices, upgrade | plan card, Stripe portal link | free, paid, past due |
| S20 | Settings | /app/settings | org, webhooks, SIEM export, retention | form sections | default |
| S21 | Onboarding checklist | /app (first run) | create key -> first call -> view log | stepper | steps 1..3 |
| S22 | Global states | n/a | 404, 403, 429 quota, maintenance | full page notices | each |

## 5. Flows
- F01 Sign up and first call: S01 -> S07 -> S21 -> S11 (create key) -> S12/curl -> S14 (see log). Target: **<= 6 clicks to first logged call**.
- F02 Upgrade: S13 quota warning -> S03/S19 -> Stripe checkout -> S19. Edge: payment fails, downgrade over quota.
- F03 Add provider: S15 -> add key -> test -> set default route. Edge: invalid key, provider down.
- F04 Block investigation: S10 alert -> S17 -> S14 detail -> S16 tune rule. Edge: false positive.
- F05 Rotate key: S11 -> create new -> reveal once -> revoke old. Edge: old key still in use (last-used shown).
- F06 Invite teammate: S18 -> invite -> accept via SSO. Edge: role limits.
- F07 NEXORA handoff: onenexora.com Gateway card -> "Open Gateway" -> gateway site -> SSO session reuse (account.onenexora.com) -> S10. Edge: no org yet, signed out.
- F08 API call lifecycle (system): auth -> rate limit -> entitlement -> DLP/injection/risk -> policy -> route -> log -> respond.

## 6. Components (design step will spec)
App shell (top bar + left nav + breadcrumb + org switcher), KPI tile, time-series chart, data table (sort/filter/pagination/CSV), detail drawer, create modal, reveal-once secret field with copy, code block with language tabs, status pill (allowed/flagged/blocked), empty state, toast, banner (quota/maintenance), plan card, stepper, command/search palette, form sections, skeletons.

## 7. Inferred data model (confidence)
- Organization(id, name, plan, owner_id) high
- Member(org_id, user_id, role: owner|admin|developer|viewer) high
- ApiKey(id, org_id, name, prefix, hash, last4, scopes, created_at, last_used_at, revoked_at, rpm_limit) high
- ProviderConnection(id, org_id, provider, encrypted_credential, base_url, status, is_default) high
- Policy(id, org_id, type: rate|model_allow|dlp|injection, config json, mode: off|monitor|enforce, version) med
- RequestLog(id, org_id, key_id, ts, provider, model, status, decision, risk_score, prompt_hash, tokens_in, tokens_out, cost_micros, latency_ms, request_id) high; **no raw prompt stored by default**
- SecurityEvent(id, log_id, type, severity, rule_id, redacted_excerpt) med
- UsageDaily(org_id, key_id, day, calls, tokens, cost) rollup, high
- Subscription(org_id, stripe_ids, plan, period, quota) high
- Webhook/SiemExport(org_id, url, secret, events) low
Identity/billing live in NEXORA account service; Gateway trusts its org/user IDs (assumption; confirm).

## 8. Inspiration map (patterns, not assets)
- **Azure portal / APIM:** resource-style overview with KPI tiles + metrics, left blade nav, "keys" pages with regenerate, policy editor with inline snippets, diagnostics/logs with filters. Use: IA and density, data tables, breadcrumb, org/directory switcher.
- **Apple:** marketing restraint: one idea per section, large type, generous whitespace, product-first imagery, quiet motion, neutral palette with one accent. Use: S01-S03 only.
- **Own voice (from NEXORA):** plain, candid, "what's real today". Keep that; it is a differentiator.

## 9. Cannot / should not
- Compliance claims (SOC2, ISO, HIPAA) until real; NEXORA already avoids badge walls. Keep.
- Microsoft/Apple logos, fonts (Segoe, SF), icons, copy: not used. Use Inter/system font stack and an original icon set.
- Multi-provider routing, policy engine, DLP ML, SIEM connectors: roadmap; ship labelled "Beta/Soon" honestly.
- Hosting self-managed Kong/K8s/Keycloak manifests as shown in repo: out of MVP; managed stack instead.

## 10. Size
Screens 22, flows 8, entities 10. **Size: L** (a quarter solo; MVP slice S01-S03, S10-S14, S19, F01/F02/F07 is **M**).
Hard parts: (1) streaming proxy with accurate token/cost metering, (2) multi-tenant key hashing + rate limiting in shared store (Redis) + log pipeline that scales, (3) DLP/injection detection with acceptable false-positive rate; also SSO/session handoff with NEXORA account and Stripe plan sync.

## 11. Open questions for you
1. Separate domain (e.g. `nexora-gateway.com`) or keep `gateway.onenexora.com`? Default assumed: **gateway.onenexora.com**, rebrand-ready.
2. Is NEXORA account (account.onenexora.com, looks like Clerk) the single login for the Gateway dashboard? Assumed yes.
3. Existing live gateway code: is it this repo or a separate (private) one? The live API differs from this repo.
4. Paste the ChatGPT chat text (link isn't machine-readable).
5. Stack preference: keep Python/FastAPI backend + Next.js dashboard? (recommended)
