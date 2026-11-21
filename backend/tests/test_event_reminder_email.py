from datetime import UTC, datetime
import pytest

from app.config import settings
from app.events import queue_reminders
from app.models import Company, Delivery, MarketEvent, ReminderSettings
from sqlalchemy import select


@pytest.mark.parametrize(("run_day", "days_left"), [(18, 7), (21, 4), (24, 1)])
def test_event_reminder_says_what_and_when_without_raw_notes_or_source(
    sessions, monkeypatch, run_day, days_left
):
    monkeypatch.setattr(settings, "resend_api_key", "test-no-real-email")
    monkeypatch.setattr(settings, "email_from", "test@example.com")
    monkeypatch.setattr(settings, "alert_email", "recipient@example.com")
    monkeypatch.setattr(settings, "app_origin", "http://localhost:5174")

    with sessions.begin() as s:
        company = s.scalar(select(Company).where(Company.ticker == "CACI"))
        s.add(
            ReminderSettings(
                id=1,
                enabled=True,
                days=[7, 1],
                categories=["earnings"],
                hour=9,
            )
        )
        s.add(
            MarketEvent(
                key="earnings:caci:2026q4",
                outcome={},
                provider="alphavantage",
                category="earnings",
                title="CACI earnings",
                day="2026-11-25",
                starts_at=None,
                source_url="https://example.test/opaque-provider-payload",
                status="estimated",
                notes="Provider-estimated earnings date for CACI International Inc. May change.",
                revision="revision-1",
                active=True,
                company_id=company.id,
            )
        )

    queue_reminders(
        sessions,
        current=datetime(2026, 11, run_day, 14, 0, tzinfo=UTC),
    )

    with sessions() as s:
        payload = s.scalar(select(Delivery)).payload

    suffix = "day" if days_left == 1 else "days"
    assert payload["subject"] == f"Reminder: CACI earnings in {days_left} {suffix}"
    assert "Upcoming calendar event" in payload["text"]
    assert "Date: Nov 25, 2026" in payload["text"]
    assert f"Reminder: {days_left} {suffix} before" in payload["text"]
    assert "This earnings date is estimated and may change." in payload["text"]
    assert "Open your investment calendar: http://localhost:5174" in payload["text"]
    assert "opaque-provider-payload" not in payload["text"]
    assert "Provider-estimated earnings date" not in payload["text"]
