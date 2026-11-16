"""Earnings scheduling from a shared provider, with no issuer-specific behavior."""

from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from uuid import uuid4
from .models import Company, Filing, Observation, CalendarCache
from .db import SessionLocal
from .config import settings
from .market_data import AlphaVantageCalendar, CalendarError


def report_loaded(filing, event):
    return bool(
        filing
        and event.get("fiscal_period")
        and filing.report_date >= event["fiscal_period"]
    )


def pending_event(state, current, filing):
    if state.get("provider") != "alphavantage" or not state.get("date"):
        return False
    day = date.fromisoformat(state["date"])
    return day <= current.date() <= day + timedelta(
        days=settings.earnings_followup_days
    ) and not report_loaded(filing, state)


def update_calendar(sessions=SessionLocal, provider=None, current=None):
    current = current or datetime.now(timezone.utc)
    with sessions() as s:
        targets = [
            (c.id, c.ticker, dict(c.earnings_schedule or {}))
            for c in s.scalars(select(Company))
        ]
    if not targets:
        return
    cached = shared_calendar(sessions, provider, current)
    if cached is None:
        return
    events, error, revision = cached
    due = [
        (identity, ticker, state)
        for identity, ticker, state in targets
        if state.get("provider") != "alphavantage"
        or state.get("checked_at") != revision
    ]
    with sessions.begin() as s:
        for identity, ticker, previous in due:
            company = s.scalar(
                select(Company).where(Company.id == identity).with_for_update()
            )
            if not company:
                continue
            state = dict(company.earnings_schedule or {})
            if state.get("provider") != "alphavantage":
                state = {"provider": "alphavantage", "status": "unavailable"}
            filing = latest_loaded_report(s, identity)
            pending = pending_event(state, current, filing)
            if not error:
                corrections = [
                    e
                    for e in events.get(ticker.upper(), [])
                    if e.get("fiscal_period") == state.get("fiscal_period")
                    and not report_loaded(filing, e)
                ]
                if corrections:
                    state = dict(max(corrections, key=lambda e: e["date"]))
                    pending = pending_event(state, current, filing)
                if not pending:
                    choices = sorted(
                        (
                            e
                            for e in events.get(ticker.upper(), [])
                            if date.fromisoformat(e["date"]) >= current.date()
                            and not report_loaded(filing, e)
                        ),
                        key=lambda e: e["date"],
                    )
                    state = (
                        dict(choices[0])
                        if choices
                        else {"provider": "alphavantage", "status": "unavailable"}
                    )
            if (
                error
                and state.get("date")
                and not pending
                and date.fromisoformat(state["date"]) < current.date()
            ):
                state = {"provider": "alphavantage", "status": "unavailable"}
            state.update(checked_at=revision, error=error)
            company.earnings_schedule = state


def shared_calendar(sessions, provider, current):
    owner = uuid4().hex
    with sessions.begin() as s:
        cache = s.scalar(
            select(CalendarCache)
            .where(CalendarCache.provider == "alphavantage")
            .with_for_update()
        )
        if cache is None:
            try:
                with s.begin_nested():
                    cache = CalendarCache(provider="alphavantage", payload={})
                    s.add(cache)
                    s.flush()
            except IntegrityError:
                cache = s.scalar(
                    select(CalendarCache)
                    .where(CalendarCache.provider == "alphavantage")
                    .with_for_update()
                )
        if cache.lease_until and cache.lease_until > current.isoformat():
            return None
        key_added = (
            bool(settings.alphavantage_api_key)
            and cache.error == "Set ALPHAVANTAGE_API_KEY to enable earnings dates."
        )
        if (
            cache.last_attempt
            and not cache.owner
            and not key_added
            and current - datetime.fromisoformat(cache.last_attempt)
            < timedelta(hours=settings.calendar_refresh_hours)
        ):
            return cache.payload, cache.error, cache.last_attempt
        cache.owner = owner
        cache.lease_until = (current + timedelta(seconds=120)).isoformat()
        cache.last_attempt = current.isoformat()
    events, error = None, None
    try:
        events = (
            provider or AlphaVantageCalendar(settings.alphavantage_api_key)
        ).events()
    except CalendarError as exc:
        error = str(exc)
    with sessions.begin() as s:
        cache = s.scalar(
            select(CalendarCache)
            .where(CalendarCache.provider == "alphavantage")
            .with_for_update()
        )
        if cache.owner != owner:
            return None
        if events is not None:
            cache.payload = events
        cache.error = error
        cache.owner, cache.lease_until = None, None
        return cache.payload, cache.error, cache.last_attempt


def refresh_due(company, current, latest_filing=None):
    if not company.last_success:
        return True
    state = company.earnings_schedule or {}
    if state.get("provider") != "alphavantage" or not state.get("date"):
        return False
    day = date.fromisoformat(state["date"])
    # Calendar has a date, not a reliable release time. Start on that date and follow up daily.
    start = datetime.combine(
        day, datetime.min.time(), ZoneInfo("America/New_York")
    ) - timedelta(days=settings.earnings_lead_days)
    end = datetime.combine(
        day + timedelta(days=settings.earnings_followup_days + 1),
        datetime.min.time(),
        ZoneInfo("America/New_York"),
    )
    if not start <= current < end or report_loaded(latest_filing, state):
        return False
    last = company.last_attempt or company.last_success
    return not last or current - datetime.fromisoformat(last) >= timedelta(
        hours=settings.financial_refresh_hours
    )


def latest_loaded_report(session, company_id):
    # A submissions entry can precede its companyfacts data. Keep polling until both exist.
    loaded = (
        select(Observation.id)
        .where(
            Observation.company_id == Filing.company_id,
            Observation.period_end == Filing.report_date,
            Observation.metric == "revenue",
            Observation.value.is_not(None),
            Observation.active.is_(True),
        )
        .exists()
    )
    return session.scalar(
        select(Filing)
        .where(
            Filing.company_id == company_id,
            Filing.form.in_(["10-Q", "10-K"]),
            loaded,
        )
        .order_by(Filing.report_date.desc(), Filing.filed.desc())
        .limit(1)
    )
