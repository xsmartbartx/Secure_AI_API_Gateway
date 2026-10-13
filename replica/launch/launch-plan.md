# Launch plan

Do not launch publicly until `replica/parity.md` verdict is shippable (SSO, streaming, usage per key, Redis/Postgres/Stripe verified, legal reviewed).

## Before
1. Private beta: 10 people you can talk to (developers on the NEXORA waitlist, your network, AI-security communities). Give each a Pro-equivalent quota; ask for permission before quoting.
2. Analytics + error tracking live (privacy-friendly analytics, Sentry-style errors); status page at status.onenexora.com.
3. Docs: quickstart with curl/Python/Node on docs.onenexora.com; changelog.
4. Legal: Terms, Privacy, DPA reviewed; processors list complete.

## Day one
- **Hacker News "Show HN":** lead with the fix, not the product: "A hosted LLM gateway with nothing to install (and no prompt storage)". Be honest in the first comment about what is beta/roadmap. HN readers in the research complained about bloat and the supply-chain incident; do not claim "more secure" than anything, state mechanics.
- **Product Hunt:** product page, honest "Beta" label, 60-second demo of key -> call -> log.
- **Where the pain is discussed** (read, then participate where rules allow; no spam): HN threads on LLM gateways, r/LocalLLaMA and r/LLMDevs (Reddit was not readable by tooling; do this by hand), GitHub discussions of gateway projects (be a helpful answer, never hijack issues).
- NEXORA homepage: Gateway card -> gateway.onenexora.com; blog post "What Gateway stores and what it doesn't".

## After
Weekly changelog; talk to the first 10 users by hand; track the metrics: signup -> key -> first call (target <= 6 clicks, minutes), 7-day retention, quota-hit -> upgrade.
No store listings (web SaaS). No paid ads until retention is understood.
