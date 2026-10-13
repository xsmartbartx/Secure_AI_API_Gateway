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
cd apps/api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000          # dev auth + mock upstream, SQLite

cd apps/web && npm install && npm run dev            # http://localhost:3000 (uses .env.local, see .env.example)
```
Tests: `cd apps/api && .venv/bin/python -m pytest -q` (16 tests).
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
Beta. Built: hashed keys, rate limit, quota, logs, playground, billing (Stripe test mode, code only), dashboard. Not built: streaming, provider vault, DLP/injection detection, policies, team management, SSO handoff. See `replica/backend.md` and `replica/parity.md`.
Production needs: Postgres (`alembic upgrade head`), Redis, NEXORA SSO JWKS, Stripe keys. See `.env.example`.

MIT License.
