from datetime import datetime, timezone, timedelta
import httpx
from sqlalchemy import select
from app.models import Alert, Delivery, RuleVersion
from app.notifications import queue_email, deliver_once
from app.config import settings
import pytest


@pytest.fixture(autouse=True)
def email_config(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "test-no-real-email")
    monkeypatch.setattr(settings, "email_from", "test@example.com")
    monkeypatch.setattr(settings, "alert_email", "recipient@example.com")


def seed(sessions):
    with sessions.begin() as s:
        rule = RuleVersion(
            company_id=1,
            group_key="test",
            version=1,
            name="Growth",
            metric="revenue_growth",
            operator="lt",
            threshold=10,
        )
        s.add(rule)
        s.flush()
        alert = Alert(
            company_id=1,
            rule_id=rule.id,
            observation_key="x",
            title="Growth: condition met",
            evidence={"value": 5},
        )
        s.add(alert)
        s.flush()
        queue_email(s, alert)


def test_alert_and_delivery_rollback_together(sessions):
    with pytest.raises(RuntimeError):
        with sessions.begin() as s:
            a = Alert(
                company_id=1, rule_id=99, observation_key="x", title="test", evidence={}
            )
            # Use a real rule for databases enforcing foreign keys.
            rule = RuleVersion(
                company_id=1,
                group_key="x",
                version=1,
                name="x",
                metric="revenue",
                operator="lt",
                threshold=10,
            )
            s.add(rule)
            s.flush()
            a.rule_id = rule.id
            s.add(a)
            s.flush()
            queue_email(s, a)
            raise RuntimeError("rollback")
    with sessions() as s:
        assert s.scalar(select(Delivery)) is None
        assert s.scalar(select(Alert)) is None


def test_retry_reuses_key_then_accepts(sessions):
    seed(sessions)
    keys = []

    def provider(request):
        keys.append(request.headers["idempotency-key"])
        return (
            httpx.Response(503)
            if len(keys) == 1
            else httpx.Response(200, json={"id": "receipt"})
        )

    transport = httpx.MockTransport(provider)
    assert deliver_once(sessions, transport)
    with sessions.begin() as s:
        row = s.scalar(select(Delivery))
        assert row.status == "pending"
        row.available_at = "2000-01-01T00:00:00+00:00"
    assert deliver_once(sessions, transport)
    assert keys[0] == keys[1]
    with sessions() as s:
        row = s.scalar(select(Delivery))
        assert row.status == "accepted" and row.provider_id == "receipt"
    assert not deliver_once(sessions, transport)


def test_expired_uncertain_request_never_sent(sessions):
    seed(sessions)
    with sessions.begin() as s:
        row = s.scalar(select(Delivery))
        row.first_attempt = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

    def provider(request):
        pytest.fail("Expired request must not be sent")

    assert deliver_once(sessions, httpx.MockTransport(provider))
    with sessions() as s:
        assert s.scalar(select(Delivery)).status == "uncertain"


def test_permanent_rejection_not_retried(sessions):
    seed(sessions)
    assert deliver_once(sessions, httpx.MockTransport(lambda r: httpx.Response(403)))
    with sessions() as s:
        assert s.scalar(select(Delivery)).status == "failed"
    assert not deliver_once(sessions)


def test_recover_expired_lease(sessions):
    seed(sessions)
    with sessions.begin() as s:
        item = s.scalar(select(Delivery))
        item.status = "sending"
        item.owner = "dead-process"
        item.attempts = 1
        item.first_attempt = datetime.now(timezone.utc).isoformat()
        item.available_at = "2000-01-01T00:00:00+00:00"
        original_key = item.key

    def provider(request):
        assert request.headers["idempotency-key"] == original_key
        return httpx.Response(200, json={"id": "recovered"})

    assert deliver_once(sessions, httpx.MockTransport(provider))
    with sessions() as s:
        assert s.scalar(select(Delivery)).status == "accepted"


def test_disabled_email_has_no_outbound_request(sessions, monkeypatch):
    seed(sessions)
    monkeypatch.setattr(settings, "resend_api_key", "")
    assert not deliver_once(
        sessions, httpx.MockTransport(lambda r: pytest.fail("Disabled"))
    )


def test_rule_evaluation_queues_one_delivery_per_alert(sessions):
    from app.models import Observation
    from app.rules import evaluate_company

    seed(sessions)
    with sessions.begin() as s:
        s.add(
            Observation(
                company_id=1,
                identity="fresh",
                metric="revenue_growth",
                period_end="2026-09-30",
                kind="quarter",
                value=5,
                unit="%",
                payload={"metric": "revenue_growth", "value": "5"},
            )
        )
    with sessions.begin() as s:
        assert evaluate_company(s, 1) == 1
    with sessions.begin() as s:
        assert evaluate_company(s, 1) == 0
        # One seeded alert and one newly evaluated observation.
        assert len(list(s.scalars(select(Alert)))) == 2
        assert len(list(s.scalars(select(Delivery)))) == 2
