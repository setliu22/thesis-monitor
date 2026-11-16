"""Persist and reconcile scheduled events and durable advance reminders."""

from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .models import MarketEvent, Company, CalendarCache, ReminderSettings, Delivery
from .db import SessionLocal
from .feed_cache import cached_feed
from .event_sources import fed_events, bls_events, bea_events, election_events
from .financials import identity
from .config import settings

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
        key = data["key"]
        keys.add(key)
        revision = identity(
            {
                k: data.get(k)
                for k in ["title", "day", "starts_at", "status", "company_id"]
            }
        )
        if key in rows:
            event = rows[key]
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
        or event.revision != item.event_revision
        or not prefs.enabled
        or event.category not in prefs.categories
        or item.reminder_days not in prefs.days
    ):
        return False
    company = s.get(Company, event.company_id) if event.company_id else None
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
            for lead in prefs.days:
                remind_day = event_day - timedelta(days=lead)
                if remind_day != local.date() or local.hour < prefs.hour:
                    continue
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
                expires = (
                    datetime.combine(
                        remind_day + timedelta(days=1),
                        time.min,
                        ZoneInfo("America/New_York"),
                    )
                    .astimezone(timezone.utc)
                    .isoformat()
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
                            "subject": f"{event.title} — in {lead} day"
                            + ("s" if lead != 1 else ""),
                            "text": f"{event.title}\nDate: {event.day} (America/New_York)\nStatus: {event.status}\n\n{event.notes}\n\nSource: {event.source_url}\n\nScheduled event reminder; no prediction of market direction.",
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
