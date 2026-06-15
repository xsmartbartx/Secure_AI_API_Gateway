# Secure AI API Gateway Setup Manual

This document contains the implementation files, structural blueprints, and deployment operations manuals necessary to stand up a modular, secure, and production-ready **AI API Gateway** utilizing Python and FastAPI.

---

## 🏗️ Core Architecture Overview

The gateway acts as an intermediary layer between your application runtimes and upstream foundational AI providers. It standardizes communications into a unified schema contract, obfuscates sensitive API credentials, validates structural JSON types, and enforces an in-memory sliding-window request limit.

```text
┌─────────────────┐       Unified Request        ┌────────────┐       Vendor Request        ┌───────────────────┐
│   Client App    │ ───────────────────────────> │ AI Gateway │ ──────────────────────────> │ Upstream Provider │
│ (Gateway Token) │ <─────────────────────────── │ (Auth/Rate)│ <────────────────────────── │ (OpenAI/Anthropic)│
└─────────────────┘       Unified Response       └────────────┘       Vendor Response       └───────────────────┘
```

### 📂 Project Directory Structure

Ensure your workspace directory layout conforms to this structural schema:

```text
secure-ai-gateway/
├── app/
│   ├── __init__.py
│   ├── config.py          # Secure environment and configuration management
│   ├── main.py            # Main API setup and routing entrypoint
│   ├── middleware.py      # Authorization, rate-limiting, and metric logging
│   ├── schemas.py         # Unified structural models for validation
│   └── adapters/
│       ├── __init__.py
│       ├── base.py        # Structural contract for upstream providers
│       ├── openai_adapter.py
│       └── anthropic_adapter.py
├── .env                  # Operational environment configurations (Git ignored)
├── .env.example           # Shared layout configuration reference
└── requirements.txt       # Engine environment dependencies
```

---

## 🛠️ Operational Instructions & Local Startup

1. **Populate Files:** Replicate the blueprint code files across your target project workspace matching the structure.
2. **Instantiate Environment Secrets:** Move your template variables file into production use:
   ```bash
   cp .env.example .env
   ```
   Provide valid API provider authentication key variables directly into `.env`.
3. **Initialize Virtual Space Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. **Boot Up application proxy runtime listener:**
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

---

## 🧪 Verification & Integration Vectors

### Target Proxy Connection Testing (OpenAI Variant):
```bash
curl -X POST [http://127.0.0.1:8000/v1/chat/completions](http://127.0.0.1:8000/v1/chat/completions) \
  -H "Authorization: Bearer sk_gateway_dev_secret_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openai",
    "model": "gpt-4o",
    "temperature": 0.2,
    "max_tokens": 100,
    "messages": [
      {"role": "system", "content": "You are a concise test assistant."},
      {"role": "user", "content": "Confirm connection status."}
    ]
  }'
```

### Target Proxy Connection Testing (Anthropic Variant):
```bash
curl -X POST [http://127.0.0.1:8000/v1/chat/completions](http://127.0.0.1:8000/v1/chat/completions) \
  -H "Authorization: Bearer sk_gateway_dev_secret_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "anthropic",
    "model": "claude-3-5-sonnet",
    "temperature": 0.5,
    "max_tokens": 150,
    "messages": [
      {"role": "user", "content": "Hello Claude! Acknowledge receipt."}
    ]
  }'
```