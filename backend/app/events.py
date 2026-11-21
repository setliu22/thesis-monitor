"""Persist and reconcile scheduled events and durable advance reminders."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .config import settings
from .db import SessionLocal
from .email_templates import event_reminder_email_content
from .event_sources import bea_events, bls_events, election_events, fed_events
from .feed_cache import cached_feed
from .financials import identity
from .models import CalendarCache, Company, Delivery, MarketEvent, ReminderSettings

CATEGORIES = ["earnings", "fed", "inflation", "employment", "gdp", "election"]


def preferences(s):
    row = s.get(ReminderSettings, 1)
    if row is None:
        try:
            with s.begin_nested():
                row = ReminderSettings(
                    id=1,
                    enabled=True,
                    days=[7, 1],
                    categories=CATEGORIES.copy(),
                    hour=9,
                )
                s.add(row)
                s.flush()
        except IntegrityError:
            row = s.get(ReminderSettings, 1)
    return row


def reconcile(s, provider, events):
    rows = {
        e.key: e
        for e in s.scalars(select(MarketEvent).where(MarketEvent.provider == provider))
    }
    keys = set()
    for data in events:
        data = dict(data)
        if provider == "bea" and data["title"].lower().startswith(
            ("gdp (", "gross domestic product")
        ):
            data["category"] = "gdp"
        key = data["key"]
        keys.add(key)
        revision = identity(
            {
                k: data.get(k)
                for k in [
                    "title",
                    "day",
                    "starts_at",
                    "status",
                    "company_id",
                    "category",
                ]
            }
        )
        if key in rows:
            event = rows[key]
            fields = ["title", "day", "starts_at", "status", "company_id", "category"]
            if any(getattr(event, field) != data.get(field) for field in fields):
                event.outcome = {}
            elif event.outcome:
                event.outcome = dict(event.outcome) | {"event_revision": revision}
            for k, v in data.items():
                setattr(event, k, v)
            event.active = True
            event.revision = revision
        else:
            s.add(
                MarketEvent(**data, provider=provider, revision=revision, active=True)
            )
    # Preserve past history; remove future events that disappear from a successful source response.
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    for key, event in rows.items():
        if key not in keys and event.day >= today:
            event.active = False


def refresh_events(sessions=SessionLocal):
    for name, loader in [
        ("fed", fed_events),
        ("bls", bls_events),
        ("bea", bea_events),
        ("election", election_events),
    ]:
        payload, error = cached_feed("events-" + name, loader, sessions=sessions)
        # A failed source must not withdraw its previously saved dates.
        if not error and "events" in payload:
            with sessions.begin() as s:
                reconcile(s, name, payload["events"])
    with sessions.begin() as s:
        cache = s.scalar(
            select(CalendarCache).where(CalendarCache.provider == "alphavantage")
        )
        if cache and not cache.error:
            events = []
            for company in s.scalars(select(Company).where(Company.watched.is_(True))):
                for data in cache.payload.get(company.ticker, []):
                    events.append(
                        dict(
                            key=f"earnings:{company.id}:{data['fiscal_period']}",
                            category="earnings",
                            title=f"{company.ticker} earnings",
                            day=data["date"],
                            starts_at=None,
                            source_url=data["source"],
                            status="estimated",
                            notes=f"Provider-estimated earnings date for {company.name}. May change.",
                            company_id=company.id,
                        )
                    )
            reconcile(s, "alphavantage", events)


def reminder_allowed(s, item, current):
    if item.expires_at and current.isoformat() >= item.expires_at:
        return False
    if item.event_id is None:
        if item.alert_id is None:
            return True
        from .models import Alert

        alert = s.get(Alert, item.alert_id)
        company = s.get(Company, alert.company_id) if alert else None
        return bool(company and company.watched)
    event = s.get(MarketEvent, item.event_id)
    prefs = preferences(s)
    if (
        not event
        or not event.active
        or event.day <= current.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        or event.revision != item.event_revision
        or not prefs.enabled
        or event.category not in prefs.categories
        or item.reminder_days not in prefs.days
    ):
        return False
    company = s.get(Company, event.company_id) if event.company_id else None
    local = current.astimezone(ZoneInfo("America/New_York"))
    event_day = date.fromisoformat(event.day)
    if any(
        lead < item.reminder_days
        and (event_day - timedelta(days=lead), prefs.hour) <= (local.date(), local.hour)
        for lead in prefs.days
    ):
        return False
    return company is None or (company.watched and company.invested)


def queue_reminders(sessions=SessionLocal, current=None):
    from .notifications import configured

    if not configured():
        return
    current = current or datetime.now(timezone.utc)
    local = current.astimezone(ZoneInfo("America/New_York"))
    with sessions.begin() as s:
        prefs = preferences(s)
        # Serialize scheduling so multiple worker instances cannot duplicate inserts.
        s.scalar(
            select(ReminderSettings).where(ReminderSettings.id == 1).with_for_update()
        )
        if not prefs.enabled:
            return
        for event in s.scalars(
            select(MarketEvent).where(
                MarketEvent.active.is_(True),
                MarketEvent.day > local.date().isoformat(),
                MarketEvent.category.in_(prefs.categories),
            )
        ):
            company = s.get(Company, event.company_id) if event.company_id else None
            if company and (not company.watched or not company.invested):
                continue
            event_day = date.fromisoformat(event.day)
            due_leads = [
                lead
                for lead in prefs.days
                if (event_day - timedelta(days=lead), prefs.hour)
                <= (local.date(), local.hour)
            ]
            if not due_leads:
                continue
            lead = min(due_leads)
            expires = (
                datetime.combine(
                    event_day, time.min, ZoneInfo("America/New_York")
                )
                .astimezone(timezone.utc)
                .isoformat()
            )
            key = identity(
                {
                    "event": event.key,
                    "revision": event.revision,
                    "lead": lead,
                    "recipient": settings.alert_email,
                }
            )
            existing = s.scalar(
                select(Delivery)
                .where(Delivery.reminder_key == key)
                .with_for_update()
            )
            if existing:
                if existing.attempts == 0 and existing.status in ("pending", "cancelled"):
                    existing.expires_at = expires
                    subject, text = event_reminder_email_content(
                        event, (event_day - local.date()).days, settings.app_origin
                    )
                    existing.payload = existing.payload | {"subject": subject, "text": text}
                if (
                    existing.status == "cancelled"
                    and existing.attempts < 6
                    and (
                        not existing.first_attempt
                        or current - datetime.fromisoformat(existing.first_attempt)
                        < timedelta(hours=23)
                    )
                ):
                    existing.status = "pending"
                    existing.error = None
                    existing.available_at = current.isoformat()
                    existing.owner = None
                continue
            subject, text = event_reminder_email_content(
                event, (event_day - local.date()).days, settings.app_origin
            )
            s.add(
                Delivery(
                    event_id=event.id,
                    event_revision=event.revision,
                    reminder_days=lead,
                    reminder_key=key,
                    expires_at=expires,
                    key="reminder-" + uuid4().hex,
                    payload={
                        "from": settings.email_from,
                        "to": [settings.alert_email],
                        "subject": subject,
                        "text": text,
                    },
                )
            )


def reminder_send_at(s, item):
    if item.event_id is None:
        return None
    event = s.get(MarketEvent, item.event_id)
    if not event:
        return None
    prefs = preferences(s)
    day = date.fromisoformat(event.day) - timedelta(days=item.reminder_days)
    return datetime.combine(
        day, time(prefs.hour), ZoneInfo("America/New_York")
    ).astimezone(timezone.utc)
