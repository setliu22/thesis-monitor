"""Normal scheduler/worker entry points with isolated synthetic SEC/Groq providers."""

import json
from sqlalchemy import select, func
import httpx
import pytest

from app.models import Review, Filing, ThesisVersion, Analysis, Job, now
from app.config import settings
from app import worker, review_pipeline, scheduled_run, sec
from app.reviews import request_review, reconcile_reviews
from app.groq_runtime import GroqRunner, Limits, Deferred
from app.feed_cache import FeedError

HTML = '<ix:nonNumeric name="dei:DocumentFiscalYearFocus">2026</ix:nonNumeric><ix:nonNumeric name="dei:DocumentFiscalPeriodFocus">Q3</ix:nonNumeric><h2>Order deliveries</h2><p>Backlog increased this quarter.</p><p>Delivery dates moved into next year.</p>'


class SEC:
    facts_late = False
    downloads = 0

    def __init__(self, *args, **kwargs):
        pass

    def fetch_json(self, path):
        if "submissions" in path:
            return {
                "filings": {
                    "recent": {
                        "accessionNumber": ["0000016058-26-000001"],
                        "form": ["10-Q"],
                        "filingDate": [now()[:10]],
                        "reportDate": ["2026-09-30"],
                        "primaryDocument": ["q.htm"],
                    }
                }
            }
        if self.facts_late:
            raise RuntimeError("Synthetic company facts delayed")
        return {"facts": {}}

    def fetch_text(self, path):
        SEC.downloads += 1
        return HTML


def setup(sessions, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "mock-only")
    monkeypatch.setattr(
        settings, "sec_user_agent", "Test Investor test@testing.invalid"
    )
    monkeypatch.setattr(sec, "SecClient", SEC)
    monkeypatch.setattr(worker, "SecClient", SEC)
    monkeypatch.setattr(review_pipeline, "SecClient", SEC)
    SEC.downloads = 0
    requests = []

    def provider(request):
        body = json.loads(request.content)
        data = json.loads(body["messages"][1]["content"])
        requests.append(data)
        if "thesis" in data:
            answer = {
                "claims": [
                    {
                        "text": "Backlog will convert faster this year.",
                        "driver": "Backlog conversion",
                        "quotes": ["Backlog will convert faster this year."],
                    }
                ] if "Backlog will convert faster this year." in data["thesis"] else []
            }
        elif "targets" in data:
            decisions = []
            for t in data["targets"]:
                text = t["text"].lower()
                direction = (
                    "challenges"
                    if "moved into next year" in text or text == "no."
                    else "supports"
                    if "accelerated" in text
                    else "neutral"
                )
                decisions.append(
                    {
                        "target_id": t["id"],
                        "links": [] if "office lease" in text else [
                            {
                                "claim_id": data["claims"][0]["id"],
                                "direction": direction,
                            }
                        ],
                    }
                )
            answer = {"decisions": decisions}
        else:
            direct = [
                e
                for e in data["evidence"]
                if e["direction"] in ("supports", "challenges")
            ]
            kinds = {e["direction"] for e in direct}
            verdict = "mixed" if len(kinds) == 2 else next(iter(kinds))
            ids = [e["id"] for e in direct]
            text = "Delivery timing evidence bears on the exact conversion premise."
            answer = {
                "assessment": verdict,
                "finding": text,
                "why_it_matters": "",
                "uncertainty": "",
                "citations": ids,
                "assertions": [{"text": text, "citations": ids}],
                "temporal_comparison": False,
            }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(answer)},
                    }
                ],
                "usage": {"total_tokens": 100},
            },
        )

    def runner(sessions, key, **kw):
        return GroqRunner(
            sessions,
            key,
            transport=httpx.MockTransport(provider),
            limits=Limits(tpm=100000, tpd=1000000, rpm=1000, rpd=10000),
            max_new_requests=100,
        )

    monkeypatch.setattr(review_pipeline, "GroqRunner", runner)
    with sessions.begin() as s:
        s.add(
            ThesisVersion(
                company_id=1, version=1, body="Backlog will convert faster this year."
            )
        )
    return requests


def seed_review(sessions):
    with sessions.begin() as s:
        f = Filing(
            company_id=1,
            accession="0000016058-26-000002",
            form="10-Q",
            filed=now()[:10],
            report_date="2026-09-30",
            document="q.htm",
        )
        s.add(f)
        s.flush()
        out = request_review(s, 1, f.id, manual=True)
        return out["review"].id


def test_unattended_scheduler_discovers_and_reviews_when_facts_late_and_email_off(
    sessions, monkeypatch
):
    requests = setup(sessions, monkeypatch)
    monkeypatch.setattr(SEC, "facts_late", True)
    monkeypatch.setattr(scheduled_run, "SessionLocal", sessions)
    from app import events, event_results

    monkeypatch.setattr(events, "refresh_events", lambda *a: None)
    monkeypatch.setattr(events, "queue_reminders", lambda *a: None)
    monkeypatch.setattr(event_results, "refresh_event_results", lambda *a: None)
    assert not settings.resend_api_key
    scheduled_run.main()
    with sessions() as s:
        review = s.scalar(select(Review))
        assert review and review.state["filing_ready"]
        assert review.status == "complete"
        result = s.scalar(select(Analysis))
        assert result.result["claim_assessments"][0]["assessment"] == "challenges"
        assert s.scalar(select(func.count()).select_from(Review)) == 1
        assert s.scalar(select(func.count()).select_from(Filing)) == 1
    assert requests


@pytest.mark.parametrize("relevant", [True, False])
def test_filing_ready_then_late_call_enrichment_reuses_filing_stages(
    sessions, monkeypatch, relevant
):
    requests = setup(sessions, monkeypatch)
    monkeypatch.setattr(settings, "alphavantage_api_key", "mock-only")
    calls = [False]

    def transcript(*args, **kwargs):
        if not calls[0]:
            raise FeedError("Synthetic call not published yet")
        return {
            "symbol": "CACI",
            "quarter": "2026Q3",
            "source_url": "https://example.org/call",
            "turns": [
                {
                    "speaker": "CEO",
                    "title": "Chief executive",
                    "content": (
                        "Deliveries accelerated over the reported quarter."
                        if relevant else "We renewed the office lease."
                    ),
                }
            ],
        }

    monkeypatch.setattr(review_pipeline, "fetch_transcript", transcript)
    rid = seed_review(sessions)
    worker.process_once(sessions, kind="analysis")
    with sessions() as s:
        r = s.get(Review, rid)
        assert r.state["filing_ready"] and r.state["call"]["status"] == "pending"
        assert s.scalar(select(func.count()).select_from(Analysis)) == 1
    file_requests = len(requests)
    calls[0] = True
    with sessions.begin() as s:
        s.get(Review, rid).next_attempt = now()
    reconcile_reviews(sessions)
    worker.process_once(sessions, kind="analysis")
    with sessions() as s:
        r = s.get(Review, rid)
        assert r.status == "complete" and r.state["call"]["status"] == "included"
        results = s.scalars(select(Analysis).order_by(Analysis.id)).all()
        assert len(results) == 2
        if relevant:
            assert results[-1].result["claim_assessments"][0]["assessment"] == "mixed"
        else:
            assert results[-1].result["claim_assessments"] == results[0].result["claim_assessments"]
    assert SEC.downloads == 1
    assert any("evidence" in request for request in requests[file_requests:]) == relevant
    assert (
        sum(
            "targets" in d and any(t["source_type"] == "filing" for t in d["targets"])
            for d in requests
        )
        == 1
    )


def test_quota_restart_keeps_pinned_source_and_completed_batches(sessions, monkeypatch):
    setup(sessions, monkeypatch)
    base = review_pipeline.GroqRunner
    stopped = [False]

    def limited(*args, **kwargs):
        r = base(*args, **kwargs)

        class Pause:
            limits = r.limits

            def __call__(self, body, validate):
                if (
                    not stopped[0]
                    and "Evaluate the exact claim" in body["messages"][0]["content"]
                ):
                    stopped[0] = True
                    raise Deferred(1)
                return r(body, validate)

        return Pause()

    monkeypatch.setattr(review_pipeline, "GroqRunner", limited)
    rid = seed_review(sessions)
    worker.process_once(sessions, kind="analysis")
    with sessions.begin() as s:
        job = s.scalar(select(Job).where(Job.kind == "analysis"))
        assert job.status == "queued" and job.attempts == 0
        job.available_at = now()
    worker.process_once(sessions, kind="analysis")
    with sessions() as s:
        assert s.get(Review, rid).state["filing_ready"]
        assert s.scalar(select(func.count()).select_from(Analysis)) == 1
    assert SEC.downloads == 1


def test_publication_then_ack_restart_never_duplicates_stage(sessions, monkeypatch):
    setup(sessions, monkeypatch)
    rid = seed_review(sessions)
    from app.jobs import claim_job

    job = claim_job(sessions, "first")
    review_pipeline.run_review(sessions, job, "first")
    with sessions.begin() as s:
        s.get(Job, job.id).lease_until = "2000-01-01T00:00:00+00:00"
    worker.process_once(sessions, kind="analysis")
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Analysis)) == 1
        assert s.get(Review, rid).status == "complete"


def test_call_provider_outage_is_bounded_and_keeps_filing_readable(
    sessions, monkeypatch
):
    setup(sessions, monkeypatch)
    monkeypatch.setattr(settings, "alphavantage_api_key", "mock-only")
    from app.transcripts import TranscriptError

    def outage(*args, **kwargs):
        raise TranscriptError("Synthetic provider outage", "provider")

    monkeypatch.setattr(review_pipeline, "fetch_transcript", outage)
    rid = seed_review(sessions)
    for _ in range(3):
        worker.process_once(sessions, kind="analysis")
        with sessions.begin() as s:
            job = s.scalar(
                select(Job).where(Job.kind == "analysis").order_by(Job.id.desc())
            )
            job.available_at = now()
    with sessions() as s:
        r = s.get(Review, rid)
        assert r.status == "failed" and r.state["filing_ready"]
        assert r.state["call"]["status"] == "failed"
        assert s.scalar(select(func.count()).select_from(Analysis)) == 1
        assert s.scalar(select(Job)).attempts == 3


def test_numeric_refresh_runs_while_narrative_has_a_quota_pause(sessions, monkeypatch):
    setup(sessions, monkeypatch)
    seed_review(sessions)
    from app import ingest
    from app.jobs import enqueue_refresh
    from test_ingest import FACTS

    base = review_pipeline.GroqRunner

    def paused(*args, **kwargs):
        runner = base(*args, **kwargs)

        class Pause:
            limits = runner.limits

            def __call__(self, *args, **kwargs):
                raise Deferred(60)

        return Pause()

    monkeypatch.setattr(review_pipeline, "GroqRunner", paused)
    monkeypatch.setattr(
        ingest, "investigate", lambda facts, registry, runner=None: registry
    )
    evaluated = []
    original = ingest.evaluate_company

    def evaluate(s, cid, previous_periods=None):
        evaluated.append(cid)
        return original(s, cid, previous_periods)

    monkeypatch.setattr(ingest, "evaluate_company", evaluate)
    worker.process_once(sessions, kind="analysis")
    with sessions.begin() as s:
        enqueue_refresh(s, 1)

    class Facts(SEC):
        def fetch_json(self, path):
            return super().fetch_json(path) if "submissions" in path else FACTS

    worker.process_once(sessions, client=Facts(), kind="refresh")
    from app.models import Observation

    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Observation)) > 0
        assert s.scalar(select(Job).where(Job.kind == "analysis")).status == "queued"
        assert s.scalar(select(Job).where(Job.kind == "refresh")).status == "succeeded"
    assert evaluated == [1]


def test_thesis_edit_during_review_does_not_rebind_captured_version(
    sessions, monkeypatch
):
    setup(sessions, monkeypatch)
    rid = seed_review(sessions)
    with sessions.begin() as s:
        s.add(
            ThesisVersion(company_id=1, version=2, body="A completely different claim.")
        )
    worker.process_once(sessions, kind="analysis")
    from app.reviews import latest_status

    with sessions() as s:
        result = s.scalar(select(Analysis))
        assert result.result["thesis_version"] == 1
        assert s.get(Review, rid).thesis_id == result.thesis_id
        assert latest_status(s, 1)["status"] == "review_available"


def test_crash_after_pinning_source_resumes_without_redownload(sessions, monkeypatch):
    setup(sessions, monkeypatch)
    rid = seed_review(sessions)
    original = review_pipeline._pin
    stopped = [False]

    def crash(*args, **kwargs):
        result = original(*args, **kwargs)
        if not stopped[0]:
            stopped[0] = True
            raise RuntimeError("Synthetic crash after pin commit")
        return result

    monkeypatch.setattr(review_pipeline, "_pin", crash)
    worker.process_once(sessions, kind="analysis")
    with sessions.begin() as s:
        job = s.scalar(select(Job).where(Job.kind == "analysis"))
        job.available_at = now()
        r = s.get(Review, rid)
        assert r.state["source_url"].startswith("https://www.sec.gov/")
    worker.process_once(sessions, kind="analysis")
    with sessions() as s:
        assert s.get(Review, rid).state["filing_ready"]
    assert SEC.downloads == 1


def test_review_uses_one_model_claim_plan_across_two_filings(sessions, monkeypatch):
    requests = setup(sessions, monkeypatch)
    thesis = (
        "Backlog will convert faster this year. "
        "If these trends continue, they could also support a higher valuation."
    )
    with sessions.begin() as s:
        s.scalar(select(ThesisVersion)).body = thesis
    seed_review(sessions)
    assert worker.process_once(sessions, kind="analysis")

    with sessions.begin() as s:
        filing = Filing(
            company_id=1, accession="0000016058-26-000003", form="10-Q",
            filed=now()[:10], report_date="2026-12-31", document="q.htm",
        )
        s.add(filing)
        s.flush()
        request_review(s, 1, filing.id, manual=True)
    assert worker.process_once(sessions, kind="analysis")

    assert [request for request in requests if "thesis" in request] == [{"thesis": thesis}]
    with sessions() as s:
        results = s.scalars(select(Analysis)).all()
        assert len(results) == 2
        for result in results:
            assert [claim["text"] for claim in result.result["claims"]] == [
                "Backlog will convert faster this year."
            ]


def test_thesis_without_testable_claims_does_not_read_the_filing(sessions, monkeypatch):
    requests = setup(sessions, monkeypatch)
    with sessions.begin() as s:
        s.scalar(select(ThesisVersion)).body = "I like this business and it could be worth more."
    review_id = seed_review(sessions)
    assert worker.process_once(sessions, kind="analysis")
    assert SEC.downloads == 0
    assert len(requests) == 1
    with sessions() as s:
        assert s.get(Review, review_id).status == "complete"
        result = s.scalar(select(Analysis)).result
        assert result["claims"] == []
        assert result["claim_assessments"] == []
        assert result["no_testable_claims"] is True
