import datetime as dt
import uuid

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, TypeDecorator, UniqueConstraint
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, future=True)
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
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    external_user_id: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="developer")
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)
    __table_args__ = (UniqueConstraint("org_id", "external_user_id", name="uq_members_org_user"),)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String)
    prefix: Mapped[str] = mapped_column(String)
    key_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    last4: Mapped[str] = mapped_column(String)
    rpm_limit: Mapped[int] = mapped_column(Integer, default=60)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    revoked_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)


class RequestLog(Base):
    __tablename__ = "request_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
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
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    log_id: Mapped[str] = mapped_column(ForeignKey("request_logs.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    rule_id: Mapped[str | None] = mapped_column(String)
    redacted_excerpt: Mapped[str | None] = mapped_column(String)
    ts: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=_now)


class Subscription(Base):
    __tablename__ = "subscriptions"
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
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


class UsageDaily(Base):
    """Counts only, no content. Written when request_logs are purged so usage history and the monthly quota outlive log retention.
    key_id is a plain string (no FK) so history survives key deletion."""
    __tablename__ = "usage_daily"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
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


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    async with SessionLocal() as session:
        yield session
