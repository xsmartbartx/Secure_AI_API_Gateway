# NEXORA Gateway

A hosted, governed entry point for AI model calls: one key, authentication, rate limits, monthly quota, and an audit log, with a dashboard. Standalone product of the NEXORA platform (gateway.onenexora.com).

```
apps/api   FastAPI data plane (/v1/chat, /v1/chat/completions) + control plane (/api/*) + Stripe webhook
apps/web   Next.js dashboard and marketing site
docs/legacy  earlier Kong/Kubernetes/DeepSeek experiments (unused)
replica/   product planning: recon, architecture, schema, design tokens, test plan, parity, launch
```

## Run locally
```bash
cd apps/api && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.lock
.venv/bin/uvicorn app.main:app --port 8000          # dev auth + mock upstream, SQLite

cd apps/web && npm install && npm run dev            # http://localhost:3000 (uses .env.local, see .env.example)
```
Tests: `cd apps/api && .venv/bin/python -m pytest -q` (93 tests).
Browser tests (Playwright, real Chrome) and accessibility scans (axe): `cd apps/web && npm run e2e` (starts its own API and web server on ports 8411/3411).
CI (`.github/workflows/ci.yml`) runs all of this on every pull request and on pushes to `main`: API lint, tests, migrations (up, check, down) and `pip-audit` on Python 3.11 and 3.12; web typecheck, build and `npm audit`; and the browser suite.
With no upstream key set, dev mode answers from a built-in mock so the full loop works offline. Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` for a real provider.

## First call
Create a key in the dashboard (`/app/keys`), then:
```bash
curl http://localhost:8000/v1/chat \
  -H "Authorization: Bearer nx_live_..." -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}'
```
`POST /v1/chat/completions` accepts the same body and answers in OpenAI shape. Errors: `{"error":{"code","message","request_id"}}`.

## Status
Beta. Built: hashed keys, rate limit, quota, logs, playground, billing (Stripe test mode, code only), dashboard. Streaming: add `"stream": true` to get Server-Sent Events of OpenAI-style chunks ending in `data: [DONE]`. Not built: DLP/injection detection, policies. SSO (NEXORA account login) is built but not yet verified against the live account. See `replica/backend.md` and `replica/parity.md`.
Production needs: Postgres (`alembic upgrade head`), Redis, NEXORA SSO JWKS, Stripe keys. See `.env.example`.

MIT License.
