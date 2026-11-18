from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.models import Job
from app.jobs import enqueue_refresh, claim_job, finish_job, fail_job


def test_enqueue_deduplication_and_retry_limit(sessions):
    with sessions() as s:
        first = enqueue_refresh(s, 1)
        s.commit()
    with sessions() as s:
        assert enqueue_refresh(s, 1).id == first.id
        s.commit()
    for n in range(3):
        job = claim_job(sessions, "worker", max_attempts=3)
        assert job.attempts == n + 1
        fail_job(sessions, job.id, "worker", "network", delay=0, max_attempts=3)
    assert claim_job(sessions, "worker") is None
    with sessions() as s:
        assert s.get(Job, first.id).status == "failed"


def test_expired_lease_is_reclaimed_and_old_owner_cannot_finish(sessions):
    with sessions() as s:
        enqueue_refresh(s, 1)
        s.commit()
    first = claim_job(sessions, "dead")
    with sessions() as s:
        s.get(Job, first.id).lease_until = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
        s.commit()
    recovered = claim_job(sessions, "alive")
    assert recovered.id == first.id and recovered.attempts == 2
    assert not finish_job(sessions, first.id, "dead")
    assert finish_job(sessions, first.id, "alive")


def test_competing_claims_do_not_return_same_job(sessions):
    with sessions() as s:
        enqueue_refresh(s, 1)
        s.commit()
    assert claim_job(sessions, "one") is not None
    assert claim_job(sessions, "two") is None


def test_skip_locked_lets_another_worker_claim_other_company(sessions):
    import pytest
    from app.models import Company

    if sessions.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    with sessions() as s:
        s.add(Company(ticker="TEST", name="Synthetic Test Company", cik="0000000001"))
        s.flush()
        first = enqueue_refresh(s, 1)
        second = enqueue_refresh(s, 2)
        s.commit()
    with sessions() as blocker:
        blocker.scalar(select(Job).where(Job.id == first.id).with_for_update())
        claimed = claim_job(sessions, "competitor")
        assert claimed.id == second.id


def test_worker_processes_queue_and_persists_success(sessions):
    from app.worker import process_once
    from app.models import Company
    from test_ingest import Client

    with sessions() as s:
        job = enqueue_refresh(s, 1)
        s.commit()
    assert process_once(sessions, Client(), "test-owner")
    with sessions() as s:
        assert s.get(Job, job.id).status == "succeeded"
        assert s.get(Company, 1).last_success
    assert not process_once(sessions, Client(), "test-owner")


def test_worker_does_not_expose_database_payloads_in_job_errors(sessions, monkeypatch):
    from app.worker import process_once
    from sqlalchemy.exc import SQLAlchemyError

    def fail(*args, **kwargs):
        raise SQLAlchemyError("private thesis and generated result payload")

    monkeypatch.setattr("app.worker.ingest_company", fail)
    with sessions.begin() as s:
        job = enqueue_refresh(s, 1)
    assert process_once(sessions, owner="test-owner")
    with sessions() as s:
        error = s.get(Job, job.id).error
        assert "Database operation failed" in error
        assert "private" not in error and "payload" not in error


def test_quota_waits_do_not_exhaust_retry_budget(sessions):
    from app.jobs import defer_job

    with sessions.begin() as s:
        queued = enqueue_refresh(s, 1, "analysis", {"filing_id": 1, "thesis_id": 1})
    for _ in range(8):
        job = claim_job(sessions, "worker")
        assert job is not None
        defer_job(sessions, job.id, "worker", "Waiting for quota", 0)
    with sessions() as s:
        assert s.get(Job, queued.id).attempts == 0
        assert s.get(Job, queued.id).status == "queued"


def test_analysis_only_claim_does_not_run_financial_refresh(sessions):
    with sessions.begin() as s:
        refresh = enqueue_refresh(s, 1)
        analysis = enqueue_refresh(s, 1, "analysis", {"filing_id": 1, "thesis_id": 1})
    claimed = claim_job(sessions, "web", kind="analysis")
    assert claimed.id == analysis.id
    with sessions() as s:
        assert s.get(Job, refresh.id).status == "queued"


def test_web_activity_wakes_expired_analysis_job(sessions, monkeypatch):
    import threading
    from app import analysis_dispatch as dispatch
    from app.config import settings

    with sessions.begin() as s:
        job = enqueue_refresh(s, 1, "analysis", {"filing_id": 1, "thesis_id": 1})
        job.status = "running"
        job.owner = "dead"
        job.lease_until = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
    starts = []

    class Thread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            starts.append(True)

    monkeypatch.setattr(settings, "groq_api_key", "test")
    monkeypatch.setattr(dispatch, "SessionLocal", sessions)
    monkeypatch.setattr(dispatch, "_gate", threading.Lock())
    monkeypatch.setattr(dispatch.threading, "Thread", Thread)
    dispatch.wake_analysis()
    assert starts == [True]
    dispatch._gate.release()


def test_changed_thesis_gets_distinct_analysis_job(sessions):
    with sessions.begin() as s:
        first = enqueue_refresh(s, 1, "analysis", {"filing_id": 1, "thesis_id": 1})
        same = enqueue_refresh(s, 1, "analysis", {"filing_id": 1, "thesis_id": 1})
        changed = enqueue_refresh(s, 1, "analysis", {"filing_id": 1, "thesis_id": 2})
        assert first.id == same.id
        assert first.id != changed.id


def test_refresh_worker_bypasses_older_groq_analysis(sessions, monkeypatch):
    from app import worker

    calls = []
    with sessions.begin() as s:
        analysis = enqueue_refresh(s, 1, "analysis", {"filing_id": 1, "thesis_id": 1})
        refresh = enqueue_refresh(s, 1, "refresh")
    monkeypatch.setattr(
        worker, "ingest_company", lambda *args, **kwargs: calls.append("refresh")
    )
    assert worker.process_once(sessions, owner="data-worker", kind="refresh")
    with sessions() as s:
        assert s.get(Job, analysis.id).status == "queued"
        assert s.get(Job, refresh.id).status == "succeeded"
    assert calls == ["refresh"]


def test_groq_deferral_marks_resource_and_clears_when_work_restarts(sessions):
    from app.jobs import defer_job

    with sessions.begin() as s:
        queued = enqueue_refresh(s, 1)
    job = claim_job(sessions, "worker")
    defer_job(sessions, job.id, "worker", "Waiting for Groq", 0)
    with sessions() as s:
        assert s.get(Job, queued.id).payload["waiting_for"] == "groq"
    resumed = claim_job(sessions, "worker")
    assert "waiting_for" not in resumed.payload
