import datetime as dt
import uuid

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, TypeDecorator, UniqueConstraint, text
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from app.config import settings

# pool_pre_ping: managed Postgres (Neon, Supabase) closes idle connections; check one is alive before handing it out
engine = create_async_engine(settings.DATABASE_URL, future=True, pool_pre_ping=True,
                             **({"poolclass": NullPool} if settings.DB_DISABLE_POOL else {}))
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class UTCDateTime(TypeDecorator):
    """Always hands back timezone-aware UTC (SQLite drops tzinfo; Postgres keeps it)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=dt.timezone.utc) if value is not None and value.tzinfo is None else value


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _id() -> str:
    return str(uuid.uuid4())


ORG_ID = "organizations.id"  # the foreign-key target every org-owned table points at


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    external_org_id: Mapped[str | None] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    plan: Mapped[str] = mapped_column(String, default="free")
    monthly_call_quota: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)


class Member(Base):
    __tablename__ = "members"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey(ORG_ID, ondelete="CASCADE"), index=True)
    external_user_id: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="developer")
    status: Mapped[str] = mapped_column(String, default="active", server_default="active")  # active | suspended (Gateway-level access switch)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)
    __table_args__ = (UniqueConstraint("org_id", "external_user_id", name="uq_members_org_user"),)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey(ORG_ID, ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String)
    prefix: Mapped[str] = mapped_column(String)
    key_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    last4: Mapped[str] = mapped_column(String)
    rpm_limit: Mapped[int] = mapped_column(Integer, default=60)
    monthly_call_limit: Mapped[int | None] = mapped_column(Integer)    # optional per-key caps; NULL = no cap beyond the org quota
    monthly_token_limit: Mapped[int | None] = mapped_column(BigInteger)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    revoked_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)


class RequestLog(Base):
    __tablename__ = "request_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey(ORG_ID, ondelete="CASCADE"))
    key_id: Mapped[str | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"))
    request_id: Mapped[str] = mapped_column(String)
    ts: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)
    provider: Mapped[str | None] = mapped_column(String)
    model: Mapped[str | None] = mapped_column(String)
    status_code: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String)  # allow | flag | block | error
    risk_score: Mapped[int | None] = mapped_column(Integer)
    prompt_hash: Mapped[str | None] = mapped_column(String)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        Index("ix_logs_org_ts", "org_id", "ts"),
        Index("ix_logs_org_decision_ts", "org_id", "decision", "ts"),
    )


class SecurityEvent(Base):
    __tablename__ = "security_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey(ORG_ID, ondelete="CASCADE"), index=True)
    log_id: Mapped[str] = mapped_column(ForeignKey("request_logs.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    rule_id: Mapped[str | None] = mapped_column(String)
    redacted_excerpt: Mapped[str | None] = mapped_column(String)
    ts: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)


class Subscription(Base):
    __tablename__ = "subscriptions"
    org_id: Mapped[str] = mapped_column(ForeignKey(ORG_ID, ondelete="CASCADE"), primary_key=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String, unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, unique=True)
    plan: Mapped[str] = mapped_column(String, default="free")
    status: Mapped[str] = mapped_column(String, default="active")
    current_period_end: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    updated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now)


class StripeEvent(Base):
    """Webhook idempotency: an event id is processed at most once."""
    __tablename__ = "stripe_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    received_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)


class ProviderConnection(Base):
    """An organization's own model-provider API key. The key is encrypted (AES-GCM, bound to this row) and never returned by the API."""
    __tablename__ = "provider_connections"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey(ORG_ID, ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String)  # anthropic | openai
    label: Mapped[str] = mapped_column(String)
    credential_enc: Mapped[bytes] = mapped_column(LargeBinary)
    hint: Mapped[str] = mapped_column(String)  # "…" + last 4 characters, to tell keys apart
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="untested")  # untested | ok | failing
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)
    __table_args__ = (Index("one_default_provider_per_org", "org_id", unique=True, sqlite_where=text("is_default"), postgresql_where=text("is_default")),)


class Policy(Base):
    """An organization's rule set for one policy type. type 'model_allow': config {"models": [glob patterns]}."""
    __tablename__ = "policies"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey(ORG_ID, ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String, default="off")  # off | monitor | enforce
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now)
    __table_args__ = (UniqueConstraint("org_id", "type", name="uq_policies_org_type"),)


class AlertSent(Base):
    """One row per (organization, month, alert kind): the claim that stops the same alert going out twice."""
    __tablename__ = "alerts_sent"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey(ORG_ID, ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String)  # YYYY-MM (UTC)
    kind: Mapped[str] = mapped_column(String)   # quota_80 | quota_100
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)
    __table_args__ = (UniqueConstraint("org_id", "month", "kind", name="uq_alerts_org_month_kind"),)


class UsageDaily(Base):
    """Counts only, no content. Written when request_logs are purged so usage history and the monthly quota outlive log retention.
    key_id is a plain string (no FK) so history survives key deletion."""
    __tablename__ = "usage_daily"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey(ORG_ID, ondelete="CASCADE"))
    day: Mapped[dt.date] = mapped_column(Date)
    key_id: Mapped[str | None] = mapped_column(String)
    model: Mapped[str] = mapped_column(String, default="unknown")
    calls: Mapped[int] = mapped_column(Integer, default=0)
    billable: Mapped[int] = mapped_column(Integer, default=0)  # calls that count toward quota (decision != error)
    blocked: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(BigInteger, default=0)
    tokens_out: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (Index("ix_usage_daily_org_day", "org_id", "day"),)


async def lock_org(session: AsyncSession, org_id: str) -> None:
    """Start a serialised section for one organization: concurrent callers wait here, one at a time, until the holder's
    transaction ends (commit or rollback). A count read after this point sees every committed reservation.

    It first commits whatever transaction the session has open (a no-op for a read-only one; loaded objects stay usable), so
    the lock is the first statement of a fresh transaction. Postgres takes a row lock (`SELECT ... FOR UPDATE`). SQLite has no
    row locks, so a no-op UPDATE takes its single write lock instead; doing that after reads in the same transaction would
    deadlock, which is why the transaction is restarted."""
    await session.commit()
    if engine.dialect.name == "sqlite":
        await session.execute(update(Organization).where(Organization.id == org_id).values(id=Organization.id))
    else:
        await session.execute(select(Organization.id).where(Organization.id == org_id).with_for_update())


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    async with SessionLocal() as session:
        yield session
