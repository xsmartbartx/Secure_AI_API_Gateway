# Fixes and positioning (replica-entrepreneur)

**Sample size: 40 public items from 2 sources** (27 Hacker News comments via the official Algolia API, 13 GitHub issue titles via the public GitHub API) about LiteLLM, Portkey, Helicone, Bifrost, OpenRouter and Cloudflare AI Gateway. No star ratings. **Reddit returned 403 and was not retrieved; G2, Capterra and Trustpilot were not read.** Everything below is directional, not statistically solid. Three of the keyword-matched quotes in `feedback.md` are false positives (the pricing line from item 49658421, the "reduce data leak" line from 48942264 under privacy, and the "Tokens used by user id)" fragment) and are not used as evidence here.

## 1. What they hate
1. **Gateways are heavy and slow, and one got compromised.** (bloat/latency 8 items, 2 sources; supply chain 5 items, 2 sources)
   - "It may not be a huge resource hog, but it adds a ton of latency." https://news.ycombinator.com/item?id=49670547
   - "I was looking for an LLM gateway and saw that the most popular one had just had a massive supply chain attack, so I wrote my own." https://news.ycombinator.com/item?id=49658421
   - "[Security]: litellm PyPI package (v1.82.7 + v1.82.8) compromised — full timeline and status" https://github.com/BerriAI/litellm/issues/24518
2. **Markup on routers** (5 items, 1 source: thin).
   - "The 5% surcharge for their pricing model may not be palatable to enterprises." https://news.ycombinator.com/item?id=48339392
   - "Free? They take the same 5% fee as OpenRouter does." (first words trimmed from a longer comment; see link) https://news.ycombinator.com/item?id=48346648
3. **Data retention is unclear when a router sits in the middle** (thin, 1 source).
   - "Worth noting retention doesn't end at the model provider." https://news.ycombinator.com/item?id=48490016
4. **Streaming and provider-translation bugs** (self-host pain, 3 GitHub items).
   - "Request to stream a chat completion results in buffered response instead of stream" https://github.com/Portkey-AI/gateway/issues/290
5. **No hard spend limits** (1 item: thin). https://news.ycombinator.com/item?id=49953318

## 2. What is missing
1. **Policy and prompt-injection controls at the gateway** (4 items, 2 sources)
   - "Prompt Injection detection and alerting" https://github.com/Helicone/helicone/issues/288
   - "Implementing LLM Gateways and Policy Enforcers (PE) is the only way to contain against these attacks." https://news.ycombinator.com/item?id=48942264
2. **Per-user usage stats and alerts** (3 items). "High-level stats (e.g. Tokens used by user id)" https://github.com/Helicone/helicone/issues/223 ; "Notifications" https://github.com/Helicone/helicone/issues/218
3. **Model aliasing**: "[Feature]: Support renaming or aliasing models" https://github.com/maximhq/bifrost/issues/1058 (1 item: thin)
4. **Central gateway for company LLM access** (1 item, thin): the HN comment at https://news.ycombinator.com/item?id=49647061 describes a "centrally managed LLM gateway that handles authentication, billing and model choice".

## 3. What is unsolved
- **A hosted, governed gateway that is not a package you install and patch.** Evidence is indirect: self-host complaints plus the supply-chain thread. Thin, 2 sources. Treat as hypothesis to validate with 10 customer interviews.
- **Regulated / enterprise teams who need audit and DLP** (the architecture doc's target). Only 4 items point here. Validate before betting on it.

## Fix plan
| # | what | size | skill | evidence |
| --- | --- | --- | --- | --- |
| 1 | Hosted, zero-install gateway: no dependency to compromise; publish how keys are stored and that prompts are not stored | S (already true) -> copy | launch | supply chain 5 items, 2 sources |
| 2 | Low-latency path: measure and publish p50 overhead added by Gateway; keep logging off the hot path | M | backend | bloat/latency 8 items, 2 sources |
| 3 | Streaming that really streams (SSE passthrough) | M | build/backend | github 290 + feature gap |
| 4 | Hard spend / call limits with alerts (already have quota; add per-key budget) | S | backend | 1 item, thin |
| 5 | Prompt-injection and DLP in monitor mode, then enforce | L | backend | governance 4 items |
| 6 | Per-key / per-user usage and alerts | M | build | visibility 3 items |
| 7 | Flat, transparent pricing with no per-token markup (already: per-call plans) | S | launch | markup 5 items (thin) |
| 8 | Data-handling page: exactly what is stored, where, retention | S | launch | privacy, thin |

Added to `features.csv` (original=no): per-key spend limits, usage alerts, published latency overhead, data-handling page, model aliasing.

## Positioning (pick one)
A. **For teams burned by installing and patching an open-source gateway,** NEXORA Gateway is a hosted door with nothing to install, one key, and an audit log, so there is no package in your supply chain. *Evidence: supply chain, 5 items across 2 sources.*
B. **For teams who need to see and control what goes to models,** NEXORA Gateway logs every call and (soon) blocks leaks and injection at the door. *Evidence: governance 4 items, 2 sources.*
C. **For teams tired of per-token markup,** flat per-call pricing, you pay the provider directly. *Evidence: 5 items, 1 source (thin).*

**Recommend A, led by B.** A is true today and matches the strongest evidence; B is the roadmap that justifies the product's name. Do not claim B features until shipped (the NEXORA site already models that candour). Do not name competitors in marketing.
