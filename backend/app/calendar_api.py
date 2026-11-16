from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, inspect
from sqlalchemy.orm import Session
from .db import get_session
from .models import MarketEvent, Company, CalendarCache, ReminderSettings, Delivery
from .events import CATEGORIES, preferences
from .company_search import search_companies
from .feed_cache import FeedError
from .notifications import configured

router = APIRouter(prefix="/api")


def record(row):
    return {c.key: getattr(row, c.key) for c in inspect(row).mapper.column_attrs}


@router.get("/company-search")
def company_search(q: str = Query(min_length=1, max_length=100)):
    try:
        return search_companies(q)
    except FeedError as exc:
        raise HTTPException(503, str(exc)) from None


class HoldingInput(BaseModel):
    invested: bool


@router.put("/companies/{company_id}/holding")
def holding(company_id: int, data: HoldingInput, s: Session = Depends(get_session)):
    company = s.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    company.invested = data.invested
    s.commit()
    return record(company)


class ReminderInput(BaseModel):
    enabled: bool
    days: list[int] = Field(min_length=1, max_length=3)
    categories: list[str] = Field(max_length=6)
    hour: int = Field(ge=0, le=23)

    @field_validator("days")
    @classmethod
    def valid_days(cls, values):
        if any(v < 1 or v > 30 for v in values):
            raise ValueError("Choose reminder days between 1 and 30")
        return sorted(set(values), reverse=True)

    @field_validator("categories")
    @classmethod
    def valid_categories(cls, values):
        if any(v not in CATEGORIES for v in values):
            raise ValueError("Unknown event category")
        return list(dict.fromkeys(values))


@router.get("/reminder-settings")
def get_settings(s: Session = Depends(get_session)):
    row = preferences(s)
    s.commit()
    return record(row) | {
        "email_configured": configured(),
        "timezone": "America/New_York",
    }


@router.put("/reminder-settings")
def save_settings(data: ReminderInput, s: Session = Depends(get_session)):
    row = preferences(s)
    s.scalar(select(ReminderSettings).where(ReminderSettings.id == 1).with_for_update())
    for k, v in data.model_dump().items():
        setattr(row, k, v)
    from .events import reminder_send_at

    for item in s.scalars(
        select(Delivery).where(
            Delivery.event_id.is_not(None),
            Delivery.status == "pending",
            Delivery.attempts == 0,
        )
    ):
        due = reminder_send_at(s, item)
        if due:
            item.available_at = max(due, datetime.now(timezone.utc)).isoformat()
    s.commit()
    return record(row) | {
        "email_configured": configured(),
        "timezone": "America/New_York",
    }


@router.get("/calendar")
def calendar(
    start: date,
    end: date,
    invested_only: bool = True,
    s: Session = Depends(get_session),
):
    if (end - start).days < 0 or (end - start).days > 62:
        raise HTTPException(422, "Request at most 62 days")
    companies = {c.id: c for c in s.scalars(select(Company))}
    events = []
    for event in s.scalars(
        select(MarketEvent)
        .where(
            MarketEvent.active.is_(True),
            MarketEvent.day >= start.isoformat(),
            MarketEvent.day <= end.isoformat(),
        )
        .order_by(MarketEvent.day, MarketEvent.title)
    ):
        company = companies.get(event.company_id)
        if invested_only and company and not company.invested:
            continue
        events.append(record(event) | {"ticker": company.ticker if company else None})
    missing = [
        {"ticker": c.ticker, "name": c.name}
        for c in companies.values()
        if (not invested_only or c.invested)
        and not (c.earnings_schedule or {}).get("date")
    ]
    sources = [
        {"provider": c.provider, "checked_at": c.last_attempt, "error": c.error}
        for c in s.scalars(
            select(CalendarCache).where(
                CalendarCache.provider.in_(
                    [
                        "events-fed",
                        "events-bls",
                        "events-bea",
                        "events-election",
                        "alphavantage",
                    ]
                )
            )
        )
    ]
    return {
        "events": events,
        "missing_earnings": missing,
        "sources": sources,
        "timezone": "America/New_York",
    }
