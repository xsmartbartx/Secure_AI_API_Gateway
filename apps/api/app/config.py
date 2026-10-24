from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str = "dev"  # dev | prod
    DATABASE_URL: str = "sqlite+aiosqlite:///./gateway.db"
    DB_DISABLE_POOL: bool = False  # tests: each test has its own event loop, so connections must not be reused across tests

    # Upstream provider credentials (platform default; per-org vault comes later)
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    # In dev with no upstream key, answer from a built-in mock so the full loop is testable
    ALLOW_MOCK_UPSTREAM: bool = True
    MOCK_PROVIDER_CHECK: bool = False  # dev/e2e: accept provider keys without calling the provider (keys containing "bad" are rejected); ignored in prod
    MOCK_STREAM_DELAY_MS: int = 0  # dev: slow the mock stream to watch it arrive or test disconnects

    # Control-plane auth (NEXORA account SSO). JWKS URL + issuer verify session JWTs in prod.
    AUTH_JWKS_URL: str = ""
    AUTH_ISSUER: str = ""
    # Dev only: trust X-Dev-Org / X-Dev-User headers. Ignored when ENV=prod.
    DEV_AUTH: bool = True

    REDIS_URL: str = ""  # empty = in-memory limiter (dev/tests only)

    # Stripe (test keys until deploy). Empty = billing disabled.
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_STARTER: str = ""
    APP_URL: str = "http://localhost:3000"

    CORS_ORIGINS: str = "http://localhost:3000,https://gateway.onenexora.com"
    # Email alerts (80% / 100% of the monthly quota) through Resend. Empty key = no email; the dashboard banner still shows.
    RESEND_API_KEY: str = ""
    ALERT_FROM_EMAIL: str = ""  # e.g. "NEXORA Gateway <alerts@your-verified-domain>"

    # 32 random bytes, base64. Encrypts customers' provider API keys at rest (AES-256-GCM). Required when ENV=prod.
    CREDENTIAL_ENCRYPTION_KEY: str = ""

    # NEXORA account (Clerk/Svix) webhook signing secret, `whsec_...`. Empty = /webhooks/account refuses all requests.
    ACCOUNT_WEBHOOK_SECRET: str = ""

    RETENTION_JOB_ENABLED: bool = True
    RETENTION_INTERVAL_HOURS: int = 24
    DEFAULT_RPM: int = 60
    FREE_MONTHLY_QUOTA: int = 100

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
