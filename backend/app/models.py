from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    Numeric,
    JSON,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Entity(Base):
    __abstract__ = True
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class Company(Entity):
    __tablename__ = "companies"
    ticker: Mapped[str] = mapped_column(String(15), unique=True)
    name: Mapped[str] = mapped_column(String(250))
    cik: Mapped[str] = mapped_column(String(10))
    last_success: Mapped[str | None] = mapped_column(String(40))
    last_attempt: Mapped[str | None] = mapped_column(String(40))
    data_status: Mapped[str] = mapped_column(String(30), default="empty")
    invested: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    earnings_schedule: Mapped[dict] = mapped_column(JSON, default=dict)


class ThesisVersion(Entity):
    __tablename__ = "theses"
    __table_args__ = (UniqueConstraint("company_id", "version"),)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)


class RuleVersion(Entity):
    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("company_id", "group_key", "version"),)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    group_key: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    metric: Mapped[str] = mapped_column(String(50))
    operator: Mapped[str] = mapped_column(String(10))
    period_kind: Mapped[str] = mapped_column(String(10), default="quarter")
    threshold: Mapped[Decimal] = mapped_column(Numeric(30, 8))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Snapshot(Entity):
    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("company_id", "kind", "digest"),)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    digest: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)


class Filing(Entity):
    __tablename__ = "filings"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "accession", name="uq_filings_company_accession"
        ),
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    accession: Mapped[str] = mapped_column(String(30))
    form: Mapped[str] = mapped_column(String(10))
    filed: Mapped[str] = mapped_column(String(10))
    report_date: Mapped[str] = mapped_column(String(10), default="")
    document: Mapped[str] = mapped_column(String(250))


class Fact(Entity):
    __tablename__ = "facts"
    __table_args__ = (UniqueConstraint("company_id", "identity"),)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    identity: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)


class Observation(Entity):
    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("company_id", "identity"),)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    identity: Mapped[str] = mapped_column(String(64))
    metric: Mapped[str] = mapped_column(String(50), index=True)
    period_end: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(10))
    value: Mapped[Decimal | None] = mapped_column(Numeric(30, 8))
    unit: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Job(Entity):
    __tablename__ = "jobs"
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="refresh")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[str] = mapped_column(String(40), default=now)
    lease_until: Mapped[str | None] = mapped_column(String(40))
    owner: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[str | None] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Analysis(Entity):
    __tablename__ = "analyses"
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"))
    thesis_id: Mapped[int] = mapped_column(ForeignKey("theses.id"))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict] = mapped_column(JSON)


class Alert(Entity):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("rule_id", "observation_key"),)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"))
    observation_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(250))
    evidence: Mapped[dict] = mapped_column(JSON)
    acknowledged_at: Mapped[str | None] = mapped_column(String(40))


class AlertEvent(Entity):
    __tablename__ = "alert_events"
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"))
    kind: Mapped[str] = mapped_column(String(30))


Index("ix_jobs_due", Job.status, Job.available_at)


class Delivery(Entity):
    __tablename__ = "deliveries"
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), unique=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_events.id"), index=True
    )
    event_revision: Mapped[str | None] = mapped_column(String(64))
    reminder_days: Mapped[int | None] = mapped_column(Integer)
    reminder_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    expires_at: Mapped[str | None] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(80), unique=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[str] = mapped_column(String(40), default=now)
    first_attempt: Mapped[str | None] = mapped_column(String(40))
    owner: Mapped[str | None] = mapped_column(String(80))
    provider_id: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(String(250))


Index("ix_deliveries_due", Delivery.status, Delivery.available_at)


class CalendarCache(Entity):
    __tablename__ = "calendar_cache"
    provider: Mapped[str] = mapped_column(String(50), unique=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    last_attempt: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(80))
    lease_until: Mapped[str | None] = mapped_column(String(40))


class MarketEvent(Entity):
    __tablename__ = "market_events"
    key: Mapped[str] = mapped_column(String(250), unique=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(250))
    day: Mapped[str] = mapped_column(String(10), index=True)
    starts_at: Mapped[str | None] = mapped_column(String(40))
    source_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    notes: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), index=True
    )


class ReminderSettings(Base):
    __tablename__ = "reminder_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    days: Mapped[list] = mapped_column(JSON, default=lambda: [7, 1])
    categories: Mapped[list] = mapped_column(
        JSON,
        default=lambda: [
            "earnings",
            "fed",
            "inflation",
            "employment",
            "gdp",
            "election",
        ],
    )
    hour: Mapped[int] = mapped_column(Integer, default=9)
