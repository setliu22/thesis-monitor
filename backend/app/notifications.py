"""Transactional outbox. Provider acceptance is not proof of inbox delivery."""

import json
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import httpx
from sqlalchemy import select
from .config import settings
from .db import SessionLocal
from .models import Delivery, Company


def configured():
    return bool(
        settings.resend_api_key and settings.email_from and settings.alert_email
    )


def queue_email(session, alert):
    if not configured():
        return
    company = session.get(Company, alert.company_id)
    session.add(
        Delivery(
            alert_id=alert.id,
            key="alert-" + uuid4().hex,
            payload={
                "from": settings.email_from,
                "to": [settings.alert_email],
                "subject": f"{company.ticker}: {alert.title}"[:250],
                "text": f"{company.ticker}: {alert.title}\n\nEvidence:\n"
                + json.dumps(alert.evidence, indent=2)
                + (
                    f"\n\nOpen monitor: {settings.app_origin}"
                    if settings.app_origin
                    else ""
                ),
            },
        )
    )


def deliver_once(sessions=SessionLocal, transport=None):
    if not configured():
        return False
    owner = uuid4().hex
    current = datetime.now(timezone.utc)
    with sessions.begin() as s:
        item = s.scalar(
            select(Delivery)
            .where(
                Delivery.status.in_(["pending", "sending"]),
                Delivery.available_at <= current.isoformat(),
            )
            .order_by(Delivery.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not item:
            return False
        from .events import reminder_allowed, reminder_send_at

        if not reminder_allowed(s, item, current):
            item.status, item.error = (
                "cancelled",
                "Reminder expired, changed or disabled",
            )
            return True
        due_at = reminder_send_at(s, item)
        if due_at and due_at > current:
            item.status = "pending"
            item.available_at = due_at.isoformat()
            item.owner = None
            return True
        # Stop before provider's 24-hour idempotency retention expires.
        if item.first_attempt and current - datetime.fromisoformat(
            item.first_attempt
        ) >= timedelta(hours=23):
            item.status, item.error = (
                "uncertain",
                "Retry window expired; reconcile with provider before resending",
            )
            return True
        if item.attempts >= 6:
            item.status, item.error = (
                "failed",
                "Delivery attempts exhausted; inspect provider before retrying",
            )
            return True
        item.owner, item.status = owner, "sending"
        item.attempts += 1
        item.first_attempt = item.first_attempt or current.isoformat()
        item.available_at = (current + timedelta(seconds=120)).isoformat()
        identity, key, payload, attempts = (
            item.id,
            item.key,
            item.payload,
            item.attempts,
        )
    status, error, provider_id = "pending", None, None
    delay = min(900, 30 * 2 ** (attempts - 1)) + random.uniform(0, 10)
    try:
        with httpx.Client(
            timeout=20, transport=transport, follow_redirects=False
        ) as client:
            response = client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Idempotency-Key": key,
                },
            )
        if 200 <= response.status_code < 300:
            provider_id = response.json().get("id")
            if not provider_id:
                raise ValueError("Missing provider receipt")
            status = "accepted"
        elif (
            response.status_code == 429
            or response.status_code >= 500
            or response.status_code == 409
        ):
            error = f"Provider HTTP {response.status_code}; retry scheduled"
            retry_after = response.headers.get("retry-after", "")
            if retry_after.isdigit():
                delay = max(delay, min(int(retry_after), 72000))
        else:
            status, error = (
                "failed",
                f"Provider rejected request: HTTP {response.status_code}",
            )
    except (httpx.HTTPError, ValueError):
        error = "Provider request failed or receipt missing; retry uses the same idempotency key"
    with sessions.begin() as s:
        item = s.scalar(
            select(Delivery).where(Delivery.id == identity).with_for_update()
        )
        if item.owner != owner or item.status != "sending":
            return True
        item.status, item.error, item.provider_id = status, error, provider_id
        item.available_at = (
            datetime.now(timezone.utc) + timedelta(seconds=delay)
        ).isoformat()
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            if not deliver_once():
                time.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception:
            logging.exception("notification_loop_failed")
            time.sleep(5)


if __name__ == "__main__":
    main()
