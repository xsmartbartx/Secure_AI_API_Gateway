# Pricing (read 2026-10-13)

## Public pricing of alternatives (from their own pages, fetched today)
| product | free tier | paid | fees | source |
| --- | --- | --- | --- | --- |
| Portkey | Developer: free, 10k recorded logs/mo, 3-day log retention; "not suitable for production" per the page | Production $49/mo, 100k logs/mo, 30-day retention; Enterprise custom | overage $9 per extra 100k | https://portkey.ai/pricing |
| Helicone | Hobby: 10,000 requests, 7-day retention | Pro $79/mo; Team $799/mo (SOC-2/HIPAA); Enterprise custom | usage-based above 10k | https://www.helicone.ai/pricing |
| Cloudflare AI Gateway | core features free on all plans | logs per Workers Logs pricing | 5% fee on unified-billing credits | https://developers.cloudflare.com/ai-gateway/reference/pricing/ |
| OpenRouter | Free plan | pay-as-you-go | 5.5% (Standard) / 8% (Business) fee on credits; BYOK free up to $25k/mo list inference, then 5% | https://openrouter.ai/pricing |
| **NEXORA Gateway (live)** | Free $0, **100 calls/mo** | Starter from $19/mo, **1,500 calls/mo** | none; you pay your provider directly | https://onenexora.com/products/gateway |

## What users said (feedback.md, thin: 5 items, 1 source)
Markup/fees on routers is the only price theme with evidence: 5% surcharge on OpenRouter and Cloudflare credits. No evidence in the sample on per-call limits.

## Assessment (honest)
- The live free tier (100 calls) is **100x smaller** than competitors' free tiers (10k logs/requests). Starter at 1,500 calls is below the competitors' free tiers. A developer evaluating Gateway will exhaust 100 calls in an afternoon of testing. This is the biggest adoption risk in the pricing, and it is a business decision, not a code one.
- Your advantages are real and should be the message: no markup on tokens, no credit top-up fee, hosted, hash-only logging.

## Recommendation (needs your decision; site and code still use the live numbers)
| tier | for | price | included calls |
| --- | --- | --- | --- |
| Free | evaluating and side projects | $0 | **1,000 / mo**, 7-day logs |
| Starter | one team in production | $19/mo | **25,000 / mo**, 30-day logs |
| Team | several apps, roles, higher limits | $79/mo | **250,000 / mo**, RBAC, 90-day logs |
| Enterprise | audit, SSO, DPA | contact | custom |
Annual: 2 months free. Overage: none at launch; hard stop with a clear 429 and an upgrade link (users complained about surprise charges elsewhere; the sample on this is thin).
Check unit economics first: per-call cost of your infra (db write per call, Redis) must be well under $19/25k = $0.00076 per call. A write-per-call design at that price needs the log queue/batching from `backend.md`.
To apply: change `PLAN_QUOTA` in `apps/api/app/routers/billing.py`, `FREE_MONTHLY_QUOTA` in config, the plan cards in `apps/web/app/pricing/page.tsx`, and the live NEXORA product page.

## Billing behaviour already built
One-click manage/cancel via Stripe Billing Portal; downgrade on cancel by webhook; past_due keeps access during Stripe's retry; no per-seat pricing; no card form of our own.

## Stripe objects for you to create (test mode first)
Product "NEXORA Gateway Starter" with a $19/month recurring price -> `STRIPE_PRICE_STARTER`. (Team price after you decide tiers.) Webhook endpoint `/webhooks/stripe`.
