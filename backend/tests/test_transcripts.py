import httpx
import pytest
from app.transcripts import (
    fiscal_quarter,
    parse_transcript,
    select_transcript_evidence,
    fetch_transcript,
)
from app.feed_cache import FeedError


def test_fiscal_quarter_uses_xbrl_not_calendar_month():
    html = '<ix:nonNumeric name="dei:DocumentFiscalYearFocus">2027</ix:nonNumeric><ix:nonNumeric name="dei:DocumentFiscalPeriodFocus">Q1</ix:nonNumeric>'
    assert fiscal_quarter(html) == "2027Q1"
    assert fiscal_quarter(html.replace("Q1", "FY")) == "2027Q4"
    assert fiscal_quarter("<p>September 30, 2026</p>") is None
    assert fiscal_quarter(html + html.replace("2027", "2026")) is None


def test_transcript_requires_exact_company_quarter_and_valid_turns():
    p = {
        "symbol": "CACI",
        "quarter": "2027Q1",
        "transcript": [
            {"speaker": "CEO", "content": "Space sensors demand is growing."}
        ],
    }
    assert parse_transcript(p, "CACI", "2027Q1")[0]["speaker"] == "CEO"
    for bad in [
        p | {"symbol": "MSFT"},
        p | {"quarter": "2026Q1"},
        p | {"transcript": []},
        {"Information": "API limit"},
    ]:
        with pytest.raises(FeedError):
            parse_transcript(bad, "CACI", "2027Q1")


def test_selection_keeps_speaker_provenance_and_budget():
    turns = [
        {"speaker": "CEO", "content": "Space sensors demand is growing. " * 40},
        {"speaker": "Operator", "content": "Please press star one for questions."},
    ]
    selected = select_transcript_evidence(
        turns, "I own this stock for space sensors demand."
    )
    assert len(selected["text"]) <= 8000
    assert selected["passages"]
    assert all(
        p["speaker"] == "CEO" and p["text"] in turns[0]["content"]
        for p in selected["passages"]
    )


def test_provider_errors_are_safe_and_do_not_contain_key(sessions):
    transport = httpx.MockTransport(lambda r: httpx.Response(403))
    with pytest.raises(FeedError) as exc:
        fetch_transcript("CACI", "2027Q1", "secret-key", sessions, transport)
    assert "secret-key" not in str(exc.value)


def test_call_comparison_retains_exact_speaker_and_thesis_quotes():
    import json
    from app.transcripts import compare_transcript
    from app.analysis import AnalysisConfig

    thesis = "I own the stock for space sensors demand."
    source = {
        "symbol": "CACI",
        "quarter": "2026Q3",
        "source_url": "https://example.org/source",
        "turns": [
            {
                "turn": 1,
                "speaker": "CEO",
                "title": "Chief executive",
                "content": "Space sensors demand is growing.",
            }
        ],
    }

    def model(request):
        body = json.loads(request.content)
        user = json.loads(body["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "matches": {
                                        p["id"]: "T1" for p in user["filing_passages"]
                                    }
                                }
                            )
                        },
                    }
                ]
            },
        )

    result = compare_transcript(
        source, thesis, AnalysisConfig("test"), httpx.MockTransport(model)
    )
    assert result["status"] == "included"
    assert result["observations"][0]["speaker"] == "CEO"
    assert result["observations"][0]["quote"] == source["turns"][0]["content"]
    assert result["observations"][0]["thesis_quote"] == thesis


def test_job_keeps_filing_comparison_if_transcript_is_unavailable(
    sessions, monkeypatch
):
    from app import analysis, transcripts
    from app.models import Filing, ThesisVersion, Job, Analysis
    from app.jobs import after
    from sqlalchemy import select

    with sessions.begin() as s:
        f = Filing(
            company_id=1,
            accession="0000016058-26-000001",
            form="10-Q",
            filed="2026-10-22",
            report_date="2026-09-30",
            document="test.htm",
        )
        t = ThesisVersion(
            company_id=1, version=1, body="Space sensors demand supports my thesis."
        )
        s.add_all([f, t])
        s.flush()
        job = Job(
            company_id=1,
            kind="analysis",
            status="running",
            owner="test",
            lease_until=after(300),
            payload={"filing_id": f.id, "thesis_id": t.id},
        )
        s.add(job)
        s.flush()
        s.expunge(job)
    monkeypatch.setattr(
        analysis, "analysis_config", lambda: analysis.AnalysisConfig("test")
    )
    monkeypatch.setattr(
        analysis.SecClient,
        "fetch_text",
        lambda *a: (
            '<ix:nonNumeric name="dei:DocumentFiscalYearFocus">2027</ix:nonNumeric><ix:nonNumeric name="dei:DocumentFiscalPeriodFocus">Q1</ix:nonNumeric><p>Space sensors demand is growing.</p>'
        ),
    )
    monkeypatch.setattr(
        analysis, "analyze_filing", lambda *a, **kw: {"observations": []}
    )

    def unavailable(*args, **kw):
        raise FeedError("Transcript is not published yet.")

    monkeypatch.setattr(transcripts, "fetch_transcript", unavailable)
    analysis.run_analysis_job(sessions, job, "test")
    with sessions() as s:
        saved = s.scalar(select(Analysis))
        assert saved.result["transcript"]["status"] == "unavailable"
        assert saved.result["transcript"]["quarter"] == "2027Q1"
        assert saved.result["source_url"].startswith("https://www.sec.gov/")


def test_substring_quote_does_not_inherit_another_speaker():
    import json
    from app.transcripts import compare_transcript
    from app.analysis import AnalysisConfig

    source = {
        "symbol": "CACI",
        "quarter": "2026Q3",
        "source_url": "https://example.org",
        "turns": [
            {
                "turn": 1,
                "speaker": "Analyst",
                "content": "Your presentation says Space demand is growing.",
            },
            {"turn": 2, "speaker": "CEO", "content": "Space demand is growing."},
        ],
    }

    def model(request):
        user = json.loads(json.loads(request.content)["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "matches": {
                                        p["id"]: "T1" for p in user["filing_passages"]
                                    }
                                }
                            )
                        },
                    }
                ]
            },
        )

    r = compare_transcript(
        source,
        "I own the stock for space demand.",
        AnalysisConfig("test"),
        httpx.MockTransport(model),
    )
    assert (
        next(o for o in r["observations"] if o["quote"] == "Space demand is growing.")[
            "speaker"
        ]
        == "CEO"
    )


def test_full_call_batches_include_late_passages_and_keep_all_speakers():
    from app.transcripts import full_transcript_batches

    turns = [
        {
            "turn": i + 1,
            "speaker": f"Speaker {i}",
            "content": f"Warehouse operating detail number {i} is relevant to planned expansion.",
        }
        for i in range(180)
    ]
    turns.append(
        {
            "turn": 181,
            "speaker": "CFO",
            "content": "Annual warehouse openings reached twenty seven locations.",
        }
    )
    turns.append(
        {
            "turn": 182,
            "speaker": "CEO",
            "content": "Annual warehouse openings reached twenty seven locations.",
        }
    )
    batches = full_transcript_batches(turns)
    assert len(batches) > 1
    passages = [p for b in batches for p in b["passages"]]
    assert any("twenty seven" in p["text"] for p in passages)
    assert all(len(b["text"]) <= 7500 and len(b["passages"]) <= 32 for b in batches)
    repeated = next(p for p in passages if "twenty seven" in p["text"])
    assert {o["speaker"] for o in repeated["occurrences"]} == {"CFO", "CEO"}


def test_full_call_retains_short_negations_and_every_source_character():
    from app.transcripts import full_transcript_batches

    turns = [
        {
            "turn": 1,
            "speaker": "CEO",
            "content": "Not yet. Demand remains below target. No. "
            + ("Capacity is constrained. " * 70),
        },
        {"turn": 2, "speaker": "CFO", "content": "Yes."},
    ]
    batches = full_transcript_batches(turns)
    catalog = [p for b in batches for p in b["passages"]]
    for turn in turns:
        occurrences = sorted(
            [
                (o["start"], o["end"])
                for p in catalog
                for o in p["occurrences"]
                if o["turn"] == turn["turn"]
            ]
        )
        rebuilt = " ".join(turn["content"][a:b] for a, b in occurrences)
        assert rebuilt.strip() == turn["content"].strip()
    assert any(p["text"] == "Yes." for p in catalog)
