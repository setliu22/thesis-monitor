from sqlalchemy import select
from app.models import Filing, ThesisVersion, Review, Job
from app.config import settings
from app.reviews import request_review, latest_status, reconcile_reviews
import pytest


def seed(sessions, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "mock")
    with sessions.begin() as s:
        s.add(ThesisVersion(company_id=1, version=1, body="Revenue grows"))
        f = Filing(
            company_id=1,
            accession="a",
            form="10-Q",
            filed="2026-10-01",
            document="a.htm",
        )
        s.add(f)
        s.flush()
        return f.id


def test_manual_auto_identity_and_completed_reuse(sessions, monkeypatch):
    fid = seed(sessions, monkeypatch)
    with sessions.begin() as s:
        a = request_review(s, 1, fid)
        b = request_review(s, 1, fid, manual=True)
        assert a["job"].id == b["job"].id
        a["review"].status = "complete"
        assert request_review(s, 1, fid)["cached"]
    with sessions() as s:
        assert len(s.scalars(select(Review)).all()) == 1
        assert len(s.scalars(select(Job)).all()) == 1


def test_wait_states_and_no_source_leak(sessions, monkeypatch):
    with sessions() as s:
        assert latest_status(s, 1)["status"] == "waiting_for_thesis"
    fid = seed(sessions, monkeypatch)
    with sessions.begin() as s:
        review = request_review(s, 1, fid)["review"]
        review.state = {"source": "private full source", "call_status": "pending"}
        assert "private full source" not in str(latest_status(s, 1))
    monkeypatch.setattr(settings, "groq_api_key", "")
    with sessions() as s:
        assert latest_status(s, 1)["status"] == "configuration_required"
        with pytest.raises(ValueError, match="Groq"):
            request_review(s, 1, fid)


def test_catchup_does_not_launch_on_thesis_edit(sessions, monkeypatch):
    seed(sessions, monkeypatch)
    assert reconcile_reviews(sessions) == 1
    with sessions.begin() as s:
        s.add(ThesisVersion(company_id=1, version=2, body="Margins expand"))
    reconcile_reviews(sessions)
    with sessions() as s:
        assert len(s.scalars(select(Review)).all()) == 1
        assert latest_status(s, 1)["status"] == "review_available"


def test_postgres_concurrent_registration(sessions, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    if sessions.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    fid = seed(sessions, monkeypatch)

    def run(manual):
        with sessions.begin() as s:
            return request_review(s, 1, fid, manual=manual)["job"].id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(run, [False, True]))
    assert ids[0] == ids[1]


def test_due_continuation_keeps_old_thesis_and_rerun_keeps_source(
    sessions, monkeypatch
):
    fid = seed(sessions, monkeypatch)
    with sessions.begin() as s:
        result = request_review(s, 1, fid)
        review, job = result["review"], result["job"]
        old_thesis = review.thesis_id
        review.state = {"source": {"text": "immutable"}, "failures": 3}
        review.status = "failed"
        job.status = "failed"
        assert request_review(s, 1, fid)["job"] is None
        rerun = request_review(s, 1, fid, manual=True, rerun=True)
        assert rerun["review"].state == {"source": {"text": "immutable"}}
        rerun["job"].status = "succeeded"
        review.next_attempt = "2020-01-01T00:00:00+00:00"
        s.add(ThesisVersion(company_id=1, version=2, body="New thesis"))
    reconcile_reviews(sessions)
    with sessions() as s:
        jobs = s.scalars(select(Job).where(Job.status == "queued")).all()
        assert len(jobs) == 1
        assert jobs[0].payload["thesis_id"] == old_thesis


def test_reconciliation_round_robin_reaches_beyond_limit(sessions, monkeypatch):
    from app.models import Company

    seed(sessions, monkeypatch)
    with sessions.begin() as s:
        for n in range(2, 8):
            company = Company(ticker=f"T{n}", name="Test", cik=str(n).zfill(10))
            s.add(company)
            s.flush()
            s.add(ThesisVersion(company_id=company.id, version=1, body="Growth"))
            s.add(
                Filing(
                    company_id=company.id,
                    accession=f"a{n}",
                    form="10-Q",
                    filed="2026-10-01",
                    document="a.htm",
                )
            )
    for _ in range(4):
        reconcile_reviews(sessions, limit=2)
    with sessions() as s:
        assert len(s.scalars(select(Review)).all()) == 7
    # A due review on a later company, with an old thesis, also gets a turn.
    with sessions.begin() as s:
        review = s.scalar(select(Review).where(Review.company_id == 7))
        old_thesis = review.thesis_id
        review.next_attempt = "2020-01-01T00:00:00+00:00"
        for job in s.scalars(select(Job)):
            job.status = "succeeded"
        s.add(ThesisVersion(company_id=7, version=2, body="Edited"))
    for _ in range(4):
        reconcile_reviews(sessions, limit=2)
    with sessions() as s:
        job = s.scalar(select(Job).where(Job.company_id == 7, Job.status == "queued"))
        assert job.payload["thesis_id"] == old_thesis


def test_expired_call_followup_stops_without_enqueue(sessions, monkeypatch):
    fid = seed(sessions, monkeypatch)
    with sessions.begin() as s:
        result = request_review(s, 1, fid)
        result["job"].status = "succeeded"
        review = result["review"]
        review.status = "filing_ready"
        review.next_attempt = "2020-01-01T00:00:00+00:00"
        review.state = {
            "filing_ready": True,
            "call": {"status": "pending", "deadline": "2021-01-01T00:00:00+00:00"},
        }
    reconcile_reviews(sessions)
    with sessions() as s:
        review = s.scalar(select(Review))
        assert review.status == "complete"
        assert review.state["call"]["status"] == "unavailable"
        assert review.next_attempt is None
        assert not s.scalar(select(Job).where(Job.status == "queued"))


def test_expired_job_exhaustion_synchronizes_review_failure(sessions, monkeypatch):
    from app.jobs import claim_job

    fid = seed(sessions, monkeypatch)
    with sessions.begin() as s:
        result = request_review(s, 1, fid)
        result["review"].status = "processing"
        result["job"].status = "running"
        result["job"].attempts = 3
        result["job"].lease_until = "2020-01-01T00:00:00+00:00"
    assert claim_job(sessions, "replacement", kind="analysis") is None
    reconcile_reviews(sessions)
    with sessions.begin() as s:
        review = s.scalar(select(Review))
        assert review.status == "failed"
        assert "Attempt limit" in review.last_error
        assert review.next_attempt is None
        assert request_review(s, 1, fid)["job"] is None
        assert request_review(s, 1, fid, rerun=True)["job"] is not None


def test_due_review_does_not_resurrect_failed_job(sessions, monkeypatch):
    fid = seed(sessions, monkeypatch)
    with sessions.begin() as s:
        result = request_review(s, 1, fid)
        result["review"].status = "source_wait"
        result["review"].next_attempt = "2020-01-01T00:00:00+00:00"
        result["job"].status = "failed"
        result["job"].error = "Provider unavailable after retries"
    reconcile_reviews(sessions)
    with sessions() as s:
        assert s.scalar(select(Review)).status == "failed"
        assert len(s.scalars(select(Job)).all()) == 1


def test_rerun_between_result_commit_and_job_ack_keeps_complete(sessions, monkeypatch):
    from app.jobs import finish_job
    from datetime import datetime, timezone, timedelta

    fid = seed(sessions, monkeypatch)
    with sessions.begin() as s:
        result = request_review(s, 1, fid)
        review, job = result["review"], result["job"]
        review.status = "complete"
        job.status, job.owner = "running", "worker"
        job.lease_until = (
            datetime.now(timezone.utc) + timedelta(minutes=5)
        ).isoformat()
        job_id = job.id
    with sessions.begin() as s:
        result = request_review(s, 1, fid, manual=True, rerun=True)
        assert result["review"].status == "complete"
        assert result["job"].id == job_id
        assert result["cached"]
    assert finish_job(sessions, job_id, "worker")
    with sessions() as s:
        assert s.scalar(select(Review)).status == "complete"
        assert len(s.scalars(select(Job)).all()) == 1


def test_completion_estimate_includes_the_daily_token_wait():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from app.groq_runtime import Limits
    from app.reviews import completion_estimate

    at = 100000
    job = SimpleNamespace(
        payload={
            "progress": {
                "phase": "filing_assessment",
                "completed_batches": 1,
                "total_batches": 2,
            }
        },
        available_at=datetime.fromtimestamp(at + 60, timezone.utc).isoformat(),
    )
    quota = {"entries": [{"at": at - 86300, "tokens": 175000}]}
    assert completion_estimate(job, {}, quota, Limits(), at) == {
        "at": datetime.fromtimestamp(at + 126, timezone.utc).isoformat(),
        "scope": "filing",
    }


def test_manual_connection_retry_reuses_job_and_leaves_quota_wait_alone(
    sessions, monkeypatch
):
    from datetime import datetime, timedelta, timezone

    fid = seed(sessions, monkeypatch)
    now = datetime.now(timezone.utc)
    with sessions.begin() as s:
        result = request_review(s, 1, fid)
        job, review = result["job"], result["review"]
        job.payload = job.payload | {
            "last_attempt_at": now.isoformat(),
            "wait_kind": "groq_provider",
        }
        review.status = "provider_wait"
        review.next_attempt = job.available_at = (now + timedelta(minutes=10)).isoformat()

        retried = request_review(s, 1, fid, manual=True, retry_connection=True)
        assert retried["job"].id == job.id
        assert job.available_at == (now + timedelta(seconds=30)).isoformat()
        assert review.next_attempt == job.available_at

        review.status = "quota_wait"
        due = (now + timedelta(hours=1)).isoformat()
        review.next_attempt = job.available_at = due
        assert request_review(s, 1, fid, manual=True, retry_connection=True)["job"] is None
        assert job.available_at == due


def test_completion_estimate_excludes_claims_that_need_no_model_call():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from app.groq_runtime import Limits
    from app.reviews import completion_estimate

    at = 100000
    job = SimpleNamespace(
        payload={
            "progress": {
                "phase": "filing_assessment",
                "completed_batches": 1,
                "total_batches": 3,
            }
        },
        available_at=datetime.fromtimestamp(at, timezone.utc).isoformat(),
    )
    state = {
        "claims": [{"id": "C1"}, {"id": "C2"}, {"id": "C3"}],
        "filing_evidence": [
            {"claim_id": "C1", "direction": "supports"},
            {"claim_id": "C2", "direction": "neutral"},
            {"claim_ids": ["C3"], "direction": "challenges"},
        ],
    }
    assert completion_estimate(job, state, {}, Limits(), at) == {
        "at": datetime.fromtimestamp(at + 25, timezone.utc).isoformat(),
        "scope": "filing",
    }


def test_review_window_counts_reporting_periods_and_rejects_old_amendments(
    sessions, monkeypatch
):
    seed(sessions, monkeypatch)
    with sessions.begin() as s:
        filings = [
            Filing(
                company_id=1, accession=f"period-{i}", form="10-Q",
                filed=f"2026-0{i + 1}-15", report_date=f"2026-0{i + 1}-01",
                document="filing.htm",
            )
            for i in range(4)
        ]
        amendment = Filing(
            company_id=1, accession="late-amendment", form="10-Q/A",
            filed="2026-11-15", report_date="2026-01-01", document="amendment.htm",
        )
        s.add_all([*filings, amendment])
        s.flush()
        with pytest.raises(ValueError, match="four most recent"):
            request_review(s, 1, amendment.id, manual=True)
        assert request_review(s, 1, filings[1].id, manual=True)["job"]
