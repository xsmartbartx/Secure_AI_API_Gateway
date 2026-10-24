## Parity: 68.2 / 100

features 68.2  (15 counted, must-haves 8 of 14 done)

Not shippable yet: 6 must-have features are not done.

## By area, weakest first
- platform                       0.0  (1 features)
- site                          37.5  (3 features)
- billing                       50.0  (1 features)
- legal                         50.0  (1 features)
- dashboard                     87.5  (4 features)
- api                           90.0  (5 features)

## Missing, in build order
- [must] platform: NEXORA to Gateway redirect + SSO handoff, no  (Open Gateway -> /app)
- [must] site: Docs quickstart + API reference, no  (docs.onenexora.com exists)
- [must] api: Rate limiting in shared store (Redis), done  (atomic Lua script, verified vs real Redis)
- [must] billing: Billing + upgrade (Stripe), partial  (checkout/portal/webhooks coded + tested with signed fakes; needs Stripe test keys)
- [must] dashboard: Usage and cost per key/model, partial  (by model only; no cost, no per-key)
- [must] legal: Terms/Privacy/DPA reviewed by lawyer, partial  (draft placeholder pages)
- [should] site: Status page, no

## Yours, not in the original (not scored)
- Standalone gateway marketing site
- Dashboard shell (nav/org switcher/breadcrumb)
- Overview KPIs + charts
- Onboarding checklist
- OpenAI-compatible /v1/chat/completions
- Streaming (SSE)
- JSON error envelope + request id
- Multi-provider routing (OpenAI/Anthropic/Azure OpenAI)
- Provider credential vault page
- Model allowlist policy
- DLP masking/blocking (email/card/IBAN/PESEL/secrets)
- Prompt injection detection (monitor mode first)
- Risk score + decision
- Security events feed
- Team + RBAC
- Webhooks / SIEM export
- Compliance badges (SOC2/ISO)
- Self-hosted Kong/K8s/Keycloak deployment
- Microsoft/Apple branding assets

---
## Notes (2026-10-13)
- **Baseline is the live NEXORA Gateway** (`original` column), so 68.2 means "vs what NEXORA Gateway offers today". Features the live product lacks (streaming, multi-provider, DLP...) are unscored extras; they are still on the roadmap.
- **Layout diff skipped:** no reference screenshots exist (own product, redesigned on purpose). Clone screenshots were checked manually at 390px and desktop; no formal saves in `replica/clone-screens/` yet.
- **Behaviour diff:** live Gateway asks the user to create keys in Console and test in `/app` playground; the clone puts keys, playground, logs and usage in one dashboard (fewer hops). First-call loop: sign-in -> keys -> create -> call -> logs = 5 clicks (target 6).
- **Verdict: not shippable.** Blocked on user-provisioned items (SSO, Stripe test keys, Redis, Postgres) plus: docs link target, usage view, lawyer-reviewed legal, streaming.
- **Top five next:** (1) SSO handoff with NEXORA account, (2) streaming SSE, (3) usage per key + date range, (4) real Redis + Postgres + Stripe test pass, (5) Playwright e2e + axe.
