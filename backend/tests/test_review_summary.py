import json

import pytest
from app.groq_runtime import Limits

THESIS = "Backlog should convert this year. I expect margins to hold."
SAVED = {
    "claims": [{"id": "C1", "text": "Backlog should convert this year."}],
    "claim_assessments": [
        {
            "claim_id": "C1",
            "assessment": "challenges",
            "finding": "Shipments moved into next year.",
            "why_it_matters": "This could support a higher valuation.",
            "citations": ["E1"],
            "assertions": [
                {"text": "Shipments moved into next year.", "citations": ["E1"]}
            ],
        }
    ],
    "evidence": [
        {
            "id": "E1",
            "claim_id": "C1",
            "direction": "challenges",
            "quote": "Shipments moved into next year.",
            "source_type": "filing",
        }
    ],
}


def test_summary_uses_complete_thesis_and_only_cited_saved_evidence():
    from app.review_summary import build_summary_request

    body, ids = build_summary_request(THESIS, SAVED, "test-model", Limits())
    data = json.loads(body["messages"][1]["content"])
    assert data["thesis"] == THESIS
    assert ids == {("C1", "challenges"): {"E1"}}
    assert "higher valuation" not in body["messages"][1]["content"]
    assert "Shipments moved into next year." in body["messages"][1]["content"]
    assert body["max_completion_tokens"] <= 750


def test_summary_rejects_invented_citations():
    from app.review_summary import parse_summary

    raw = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {
                            "sections": [
                                {
                                    "claim_id": "C1",
                                    "direction": "challenges",
                                    "text": "Shipments slipped.",
                                    "citations": ["E99"],
                                }
                            ],
                        }
                    )
                },
            }
        ]
    }
    with pytest.raises(ValueError, match="citation"):
        parse_summary(raw, {("C1", "challenges"): {"E1"}})


def test_summary_job_reuses_saved_review_and_caches_the_result(sessions, monkeypatch):
    import httpx
    from app import review_summary, worker
    from app.config import settings
    from app.groq_runtime import GroqRunner
    from app.models import Analysis, Filing, Job, Review, ThesisVersion

    monkeypatch.setattr(settings, "groq_api_key", "mock")
    calls = []
    response = {
        "sections": [
            {
                "claim_id": "C1",
                "direction": "challenges",
                "text": "Shipments slipped.",
                "citations": ["E1"],
            }
        ]
    }

    def model_call(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(response)},
                    }
                ]
            },
        )

    def runner_factory(*args, **kwargs):
        return GroqRunner(*args, **kwargs, transport=httpx.MockTransport(model_call))

    monkeypatch.setattr(review_summary, "GroqRunner", runner_factory)
    with sessions.begin() as session:
        filing = Filing(
            company_id=1,
            accession="test",
            form="10-Q",
            filed="2026-11-01",
            document="test.htm",
        )
        thesis = ThesisVersion(company_id=1, version=1, body=THESIS)
        session.add_all([filing, thesis])
        session.flush()
        review = Review(
            company_id=1,
            filing_id=filing.id,
            thesis_id=thesis.id,
            model=settings.groq_model,
            version="test",
            status="complete",
        )
        session.add(review)
        session.flush()
        analysis = Analysis(
            company_id=1,
            filing_id=filing.id,
            thesis_id=thesis.id,
            model=settings.groq_model,
            prompt_version="test",
            review_id=review.id,
            result=SAVED,
        )
        session.add(analysis)
        session.flush()
        analysis.result = SAVED | {"summary": {"sections": [{"text": "Unsupported."}]}}
        job = review_summary.request_summary(session, 1, analysis.id, automatic=True)
        assert review_summary.request_summary(session, 1, analysis.id).id == job.id
        job.status = "failed"
        assert (
            review_summary.request_summary(session, 1, analysis.id, automatic=True)
            is None
        )
        job.status = "queued"

    assert worker.process_once(sessions, kind="analysis")
    with sessions.begin() as session:
        assert review_summary.request_summary(session, 1, analysis.id) is None
        assert session.get(Analysis, analysis.id).result == SAVED | {
            "summary": response | {"policy": review_summary.SUMMARY_POLICY}
        }
        assert session.get(Review, review.id).status == "complete"
        assert session.get(Job, job.id).status == "succeeded"
    assert len(calls) == 1


def test_inconclusive_findings_are_not_sent_even_with_directional_excerpts():
    from app.review_summary import direct_findings

    original = SAVED["claim_assessments"][0]
    inconclusive = SAVED | {
        "claim_assessments": [dict(original, assessment="insufficient evidence")],
    }
    assert list(direct_findings(inconclusive)) == []


def test_mixed_findings_require_citations_on_the_correct_side():
    from app.review_summary import build_summary_request, parse_summary

    original = SAVED["claim_assessments"][0]
    supporting = dict(
        SAVED["evidence"][0],
        id="E2",
        direction="supports",
        quote="Most orders will ship this year.",
    )
    neutral = dict(supporting, id="E3", direction="neutral")
    saved = SAVED | {
        "claim_assessments": [
            dict(original, assessment="mixed", citations=["E1", "E2", "E3"])
        ],
        "evidence": [*SAVED["evidence"], supporting, neutral],
    }
    _, allowed = build_summary_request(THESIS, saved, "test-model", Limits())
    assert allowed == {("C1", "supports"): {"E2"}, ("C1", "challenges"): {"E1"}}
    empty = {
        "choices": [
            {"finish_reason": "stop", "message": {"content": '{"sections":[]}'}}
        ]
    }
    assert parse_summary(empty, allowed)["sections"] == []
