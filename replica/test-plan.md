# Test plan (2026-10-13)

Legend: A = automated (pytest, `apps/api/tests`), M = manual in browser, - = not run.

| case | description | how | result |
| --- | --- | --- | --- |
| F01-H1 | create key -> call /v1/chat -> log appears, key shows last used | A | pass |
| F01-H2 | playground call with no key -> logged without key id, time shown correctly | A+M | pass |
| F01-E1 | empty / blank key name | A | pass (after B1) |
| F01-E2 | emoji, accents, CJK prompt | curl | pass |
| F01-E3 | 300k-char prompt | curl | pass (422 envelope) |
| F01-E4 | invalid JSON, bad role, empty messages | A+curl | pass (after B5) |
| F01-E5 | stream=true | curl | pass: clear 422, not implemented (feature gap, not bug) |
| F01-N1 | bad / missing / revoked key | A | pass |
| F01-N2 | provider not configured upstream | curl | pass: 502 `upstream_not_configured`, logged as error |
| F01-N3 | rate limit (2 rpm key) | A | pass |
| F01-N4 | monthly quota exceeded | A | pass |
| F02-H1 | webhook upgrades plan + quota 100->1500 | A (signed fake) | pass |
| F02-E1 | same webhook delivered twice | A | pass (idempotent) |
| F02-N1 | bad webhook signature | A | pass |
| F02-N2 | cancel -> downgrade to free | A | pass |
| F02-N3 | checkout with billing disabled | A | pass (503) |
| F02-H2 | real Stripe checkout, card 4242 / declined 4000 0000 0000 0002 | - | **blocked: needs Stripe test keys** |
| F05-H1 | revoke key; old key rejected | A | pass |
| F05-H2 | rotate (old stays valid until revoked) | A (api) | rotate covered by code path only; no UI, no test of "old still works" -> see T3 |
| X-1 | cross-org access to logs/keys/revoke | A | pass (empty / 404) |
| X-2 | viewer cannot create key | A | pass (403) |
| F07-H1 | NEXORA -> Gateway SSO handoff | - | **blocked: SSO not wired** |
| UI-1 | no horizontal scroll at 390px on /, /pricing, /security, /app/keys, /app/logs, /app/billing, /app/playground | M | pass |
| UI-2 | overview empty state, then filled state with chart | M | pass |
| UI-3 | console errors on visited pages | M | none |
| UI-4 | keyboard: create-key form submit by Enter; nav links focusable | M | pass |
| UI-5 | axe accessibility scan | - | not run (no Playwright/axe installed) |
| UI-6 | dark mode parity | M (OS dark) | pass visually on home, keys |

Playwright e2e was skipped as not cheap here (needs browser download + SSO stub); manual click-through used instead. Add e2e before launch.
Totals: 29 cases, 24 pass, 0 fail now, 5 blocked/not run.


## Update 2026-10-14: automated browser suite
`apps/web/e2e` (Playwright 1.64, real Chrome via `channel: 'chrome'`, run with `npm run e2e` in `apps/web`). It starts a fresh API (SQLite, mock upstream, 150 ms per streamed word) on :8411 and a production build of the web app on :3411; each test runs in its own organization and **fails on any console error or 5xx**.
- 66 tests; green on repeated runs, including one with every test run twice (no flakes).
- Flows: F01 first call (empty state, create key, reveal-once banner, call, logged row, keyboard-open drawer without prompt text, overview); blank key name; F05 revoke (+cancel the dialog, + rate limit 429/Retry-After); playground streaming (partial text before the end, Stop -> 499 "cancelled by client"); quota exhaustion (100 calls) shown in billing and playground; usage by key/model/day, totals, CSV download + formula neutralisation, invalid range; settings (typed-name delete, key dies, owner sees form); marketing pages and dead-link check; 404; favicon.
- Responsive: no horizontal scroll at 390px on 11 pages; dashboard menu opens, navigates, closes.
- **Accessibility (axe-core, WCAG 2.0/2.1/2.2 A+AA + best practices):** 17 pages x light and dark, plus the dashboard with data (keys table, key-reveal banner, logs table, open drawer). A canary test plants violations and checks axe reports them, so a clean result is not vacuous. All clean after fixing B9.
- Found by this suite and fixed: B6 (S2), B7 (S3), B8 (S2), B9 (S4).
Not covered: real Clerk sign-in, real Stripe checkout, real Anthropic/OpenAI, Stripe test mode; screen-reader and manual keyboard review beyond what axe and the keyboard tests cover (axe finds roughly a third of accessibility problems); Safari/Firefox (Chrome only); visual regression.

Update (providers): 69 browser tests now (added provider-key CRUD, developer read-only, axe on the providers page with keys); 78 API tests.

Update (export): 71 browser tests, 84 API tests.

Update (team): 75 browser tests, 93 API tests.

Update (policies): 79 browser tests, 129 API tests.

Update (detection, limits, alerts, cleanup): 90 browser tests, 210 API tests.
