import json
from types import SimpleNamespace
import pytest
from app.evidence import (
    split_claims,
    filing_targets,
    call_targets,
    find_evidence,
    assess_claims,
)
from app.groq_runtime import Limits, estimate

CONFIG = SimpleNamespace(model="mock")


class Runner:
    limits = Limits()

    def __init__(self, answer):
        self.answer = answer
        self.bodies = []

    def __call__(self, body, validate):
        assert estimate(body) <= self.limits.tpm
        self.bodies.append(body)
        raw = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            self.answer(json.loads(body["messages"][1]["content"]))
                        )
                    },
                }
            ]
        }
        validate(raw)
        return raw


def test_claims_preserve_long_and_qualifiers():
    text = (
        "Only if demand holds, conversion will accelerate next year.\n"
        + "Qualified claim " * 500
    )
    claims = split_claims(text)
    assert len(claims) == 2 and claims[0]["text"].endswith("next year.")
    assert len(claims[1]["text"]) > 4000
    with pytest.raises(ValueError):
        split_claims(" \n ")


def test_retrieval_context_and_synonyms():
    result = filing_targets(
        "<h2>Order delivery</h2><p>Our order book expanded.</p><p>These deliveries moved into next year.</p>",
        split_claims("Backlog will convert faster this year."),
        "source",
        "2026Q3",
    )
    assert result["coverage"]["selective"]
    assert any("next year" in t["text"] for t in result["targets"])
    assert result["targets"][1]["context"]["previous"] == "Our order book expanded."


def test_call_keeps_identical_answers_different_speakers():
    result = call_targets(
        {
            "turns": [
                {
                    "speaker": "Analyst",
                    "role": "analyst",
                    "content": "Will conversion accelerate?",
                },
                {"speaker": "CEO", "role": "management", "content": "No."},
                {"speaker": "CFO", "role": "management", "content": "No."},
            ]
        },
        "2026Q3",
    )
    assert len(result["targets"]) == 3
    assert result["targets"][1]["context"]["previous"]["speaker"] == "Analyst"
    claims = split_claims("Backlog will convert faster this year.")
    runner = Runner(
        lambda data: {
            "decisions": [
                {
                    "target_id": t["id"],
                    "links": [{"claim_id": "C1", "direction": "challenges"}],
                }
                for t in data["targets"]
            ]
        }
    )
    evidence = find_evidence(result, claims, CONFIG, runner)
    assert evidence[0]["direction"] == "neutral"
    assert evidence[1]["id"] != evidence[2]["id"]
    assert evidence[1]["quote"] == "No." and evidence[1]["speaker"] == "CEO"


def test_stage_a_requires_all_targets_and_valid_claims():
    claims = split_claims("Demand rises.")
    targets = call_targets({"turns": [{"speaker": "CEO", "content": "Demand rose."}]})
    with pytest.raises(ValueError):
        find_evidence(targets, claims, CONFIG, Runner(lambda data: {"decisions": []}))
    with pytest.raises(ValueError):
        find_evidence(
            targets,
            claims,
            CONFIG,
            Runner(
                lambda data: {
                    "decisions": [
                        {
                            "target_id": "T1.1",
                            "links": [{"claim_id": "C99", "direction": "supports"}],
                        }
                    ]
                }
            ),
        )


@pytest.mark.parametrize("target_id,claim_id", [([], "C1"), ("T1.1", {})])
def test_stage_a_rejects_non_string_ids_as_validation_errors(target_id, claim_id):
    claims = split_claims("Demand rises.")
    targets = call_targets({"turns": [{"speaker": "CEO", "content": "Demand rose."}]})
    runner = Runner(lambda data: {"decisions": [{
        "target_id": data["targets"][0]["id"] if isinstance(target_id, str) else target_id,
        "links": [{"claim_id": claim_id, "direction": "supports"}],
    }]})
    with pytest.raises(ValueError, match="target ID|claim link"):
        find_evidence(targets, claims, CONFIG, runner)


def test_long_thesis_partitions_every_claim():
    claims = split_claims(
        "\n".join("Demand will increase if market %s grows." % i for i in range(150))
    )
    runner = Runner(
        lambda data: {
            "decisions": [{"target_id": t["id"], "links": []} for t in data["targets"]]
        }
    )
    find_evidence(
        call_targets({"turns": [{"speaker": "CEO", "content": "Nothing material."}]}),
        claims,
        CONFIG,
        runner,
    )
    reviewed = [
        c["id"]
        for b in runner.bodies
        for c in json.loads(b["messages"][1]["content"])["claims"]
    ]
    assert set(reviewed) == {c["id"] for c in claims}
    assert len(runner.bodies) < 150


def test_neutral_no_model_and_synthesis_citation_validation():
    claims = split_claims("Backlog converts faster.")
    runner = Runner(lambda data: pytest.fail("No request for empty evidence"))
    assert (
        assess_claims(claims, [], CONFIG, runner)[0]["assessment"]
        == "insufficient evidence"
    )
    evidence = [
        {
            "id": "E1",
            "claim_id": "C1",
            "quote": "Delayed into next year.",
            "direction": "challenges",
            "period": "2026Q3",
        }
    ]

    def answer(data):
        return {
            "assessment": "challenges",
            "finding": "Delivery was delayed.",
            "why_it_matters": "",
            "uncertainty": "",
            "citations": ["E1"],
            "assertions": [{"text": "Delivery was delayed.", "citations": ["E1"]}],
            "temporal_comparison": False,
        }

    assert (
        assess_claims(claims, evidence, CONFIG, Runner(answer))[0]["assessment"]
        == "challenges"
    )

    def wrong(data):
        return answer(data) | {"assessment": "mixed"}

    with pytest.raises(ValueError):
        assess_claims(claims, evidence, CONFIG, Runner(wrong))

    def temporal(data):
        return answer(data) | {"temporal_comparison": True}

    with pytest.raises(ValueError):
        assess_claims(claims, evidence, CONFIG, Runner(temporal))


def test_single_oversized_claim_actionable():
    runner = Runner(lambda data: {})
    with pytest.raises(ValueError, match="individual claim"):
        find_evidence(
            call_targets({"turns": [{"speaker": "CEO", "content": "No."}]}),
            split_claims("word " * 40000),
            CONFIG,
            runner,
        )


def test_normal_thesis_is_one_multi_claim_request():
    claims = split_claims("Demand rises. Margins expand. Cash grows.")
    runner = Runner(
        lambda data: {
            "decisions": [
                {
                    "target_id": t["id"],
                    "links": [
                        {"claim_id": c["id"], "direction": "neutral"}
                        for c in data["claims"]
                    ],
                }
                for t in data["targets"]
            ]
        }
    )
    evidence = find_evidence(
        call_targets({"turns": [{"speaker": "CEO", "content": "Our outlook."}]}),
        claims,
        CONFIG,
        runner,
    )
    assert len(runner.bodies) == 1 and len(evidence) == 3


def test_long_question_tail_and_continuation_context():
    question = "Intro " * 200 + "Do you mean conversion improves only after next year?"
    targets = call_targets(
        {
            "turns": [
                {"speaker": "Analyst", "role": "analyst", "content": question},
                {"speaker": "CEO", "role": "management", "content": "No."},
                {
                    "speaker": "CEO",
                    "role": "management",
                    "content": "One " * 700 + "Finally.",
                },
            ]
        }
    )["targets"]
    answer = next(t for t in targets if t["text"] == "No.")
    assert answer["context"]["previous"]["text"].endswith("only after next year?")
    continuation = [t for t in targets if t["id"].startswith("T3.")][1]
    assert continuation["context"]["previous"]["speaker"] == "CEO"
    assert continuation["context"]["previous"]["text"].endswith("One")


def test_management_rhetorical_question_keeps_direction():
    runner = Runner(
        lambda d: {
            "decisions": [
                {
                    "target_id": t["id"],
                    "links": [{"claim_id": "C1", "direction": "supports"}],
                }
                for t in d["targets"]
            ]
        }
    )
    result = find_evidence(
        call_targets(
            {
                "turns": [
                    {
                        "speaker": "CEO",
                        "role": "management",
                        "content": "Is demand rising? Yes, sales doubled.",
                    }
                ]
            }
        ),
        split_claims("Demand rises."),
        CONFIG,
        runner,
    )
    assert result[0]["direction"] == "supports"


@pytest.mark.parametrize(
    "finish,refusal", [("length", None), ("stop", "Refused"), (None, None)]
)
def test_refused_or_incomplete_responses_rejected(finish, refusal):
    from app.evidence import _decode

    with pytest.raises(ValueError):
        _decode(
            {
                "choices": [
                    {
                        "finish_reason": finish,
                        "message": {"content": "{}", "refusal": refusal},
                    }
                ]
            }
        )


def test_prior_allocation_bounded_and_explicit():
    current = [
        {
            "id": "E1",
            "claim_id": "C1",
            "quote": "Current growth.",
            "direction": "supports",
            "period": "2026Q3",
        }
    ]
    prior = [
        {
            "id": f"P{i}",
            "claim_id": "C1",
            "quote": ("Earlier observation " + str(i) + " ") * 70,
            "direction": "supports" if i % 2 else "challenges",
            "period": "2025Q3",
            "comparable": True,
        }
        for i in range(100)
    ]

    def answer(data):
        assert data["prior"] and {e["direction"] for e in data["prior"]} == {
            "supports",
            "challenges",
        }
        return {
            "assessment": "supports",
            "finding": "Current growth.",
            "why_it_matters": "",
            "uncertainty": "",
            "citations": ["E1"],
            "assertions": [{"text": "Current growth.", "citations": ["E1"]}],
            "temporal_comparison": False,
        }

    result = assess_claims(
        split_claims("Demand rises."), current, CONFIG, Runner(answer), prior=prior
    )[0]
    assert (
        result["coverage"]["prior_incomplete"]
        and result["coverage"]["reviewed_prior"] < 100
    )


def test_neighboring_thesis_conditions_preserved_exactly():
    claims = split_claims(
        "Only if demand recovers. Margins can expand. This remains conditional through next year."
    )
    assert claims[1]["text"] == "Margins can expand."
    assert claims[1]["thesis_context"] == {
        "previous": "Only if demand recovers.",
        "next": "This remains conditional through next year.",
    }
    runner = Runner(
        lambda data: {
            "decisions": [{"target_id": t["id"], "links": []} for t in data["targets"]]
        }
    )
    find_evidence(
        call_targets(
            {"turns": [{"speaker": "CEO", "content": "Demand remains weak."}]}
        ),
        claims,
        CONFIG,
        runner,
    )
    supplied = json.loads(runner.bodies[0]["messages"][1]["content"])["claims"]
    assert [c["text"] for c in supplied] == [c["text"] for c in claims]
    assert all(set(c) == {"id", "text"} for c in supplied)


def test_gpt_oss_limits_reasoning_and_reserves_output_budget():
    from app.evidence import _body, STAGE_A_PROMPT

    body = _body(
        STAGE_A_PROMPT,
        {"claims": [], "targets": []},
        SimpleNamespace(model="openai/gpt-oss-20b"),
    )
    assert body["reasoning_effort"] == "low"
    assert body["max_completion_tokens"] == 3072
    assert body["response_format"]["json_schema"]["strict"] is True
    assert "reasoning_effort" not in _body(STAGE_A_PROMPT, {}, CONFIG)


def test_filing_context_bounded_and_synonym_stemming():
    from app.evidence import _terms

    assert _terms("deliveries") & _terms("backlog")
    result = filing_targets(
        "<h2>"
        + ("Heading " * 80)
        + "</h2><p>"
        + ("Deliveries " * 100)
        + "</p><p>Backlog conversion accelerated.</p><p>"
        + ("Next " * 200)
        + "</p>",
        split_claims("Backlog converts faster."),
    )
    target = next(
        t for t in result["targets"] if t["text"] == "Backlog conversion accelerated."
    )
    assert (
        len(target["context"]["previous"]) <= 400
        and len(target["context"]["next"]) <= 400
    )
    assert len(target["heading"]) <= 300 and target["context_clipped"]


def test_neutral_evidence_remains_citable_without_model():
    runner = Runner(lambda d: pytest.fail("Neutral evidence requires no model"))
    evidence = [
        {
            "id": "E-topic",
            "claim_id": "C1",
            "quote": "Backlog grew.",
            "direction": "neutral",
        }
    ]
    result = assess_claims(
        split_claims("Backlog converts faster."), evidence, CONFIG, runner
    )[0]
    assert result["assessment"] == "insufficient evidence" and result["citations"] == [
        "E-topic"
    ]


def test_incomplete_evidence_batch_retries_each_target():
    from app.groq_runtime import InvalidModelResponse

    targets = [{"id": "T1", "text": "Margin rose."}, {"id": "T2", "text": "Costs fell."}]
    calls = []

    def runner(body, validate):
        batch = json.loads(body["messages"][1]["content"])["targets"]
        calls.append([target["id"] for target in batch])
        result = {"decisions": [
            {"target_id": batch[0]["id"], "links": [{"claim_id": "C1", "direction": "supports"}]}
        ]}
        raw = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}
        try:
            validate(raw)
        except ValueError as exc:
            raise InvalidModelResponse(str(exc)) from exc
        return raw

    result = find_evidence(targets, split_claims("Margins will improve."), CONFIG, runner)
    assert calls == [["T1", "T2"], ["T1"], ["T2"]]
    assert [item["target_id"] for item in result] == ["T1", "T2"]


def test_assessment_retries_with_citations_attached_to_each_field():
    from app.groq_runtime import InvalidModelResponse

    fixture = {"id": "E1", "claim_id": "C1", "quote": "Demand fell.", "direction": "challenges"}
    attempts = []

    def runner(body, validate):
        attempts.append(body)
        if len(attempts) == 1:
            raise InvalidModelResponse("Every assertion requires supplied citations.")
        obj = {
            "assessment": "challenges",
            "temporal_comparison": False,
            "finding": {"text": "Demand fell.", "citations": ["E1"]},
            "why_it_matters": {"text": "", "citations": []},
            "uncertainty": {"text": "", "citations": []},
        }
        raw = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(obj)}}]}
        validate(raw)
        return raw

    result = assess_claims(split_claims("Demand will increase."), [fixture], CONFIG, runner)
    assert len(attempts) == 2
    assert result[0]["assessment"] == "challenges"
    assert result[0]["citations"] == ["E1"]


def test_compact_assessment_keeps_cited_finding_and_drops_uncited_optional_text():
    from app.groq_runtime import InvalidModelResponse

    claim = split_claims("Backlog converts faster.")
    sources = [
        {
            "id": "E1",
            "claim_id": "C1",
            "quote": "Delivery moved into next year.",
            "direction": "challenges",
        }
    ]

    class CompactRunner(Runner):
        def __call__(self, body, validate):
            if body["messages"][0]["content"].startswith("Treat supplied source text"):
                raise InvalidModelResponse("Every assertion requires supplied citations.")
            return super().__call__(body, validate)

    def response(finding_citations):
        return {
            "assessment": "challenges",
            "finding": {"text": "Delivery was delayed.", "citations": finding_citations},
            "why_it_matters": {"text": "This affects revenue.", "citations": []},
            "uncertainty": {"text": "The new schedule may slip again.", "citations": []},
            "temporal_comparison": False,
        }

    runner = CompactRunner(lambda data: response(["E1"]))
    result = assess_claims(claim, sources, CONFIG, runner)[0]
    assert result["assessment"] == "challenges"
    assert result["finding"] == "Delivery was delayed."
    assert result["citations"] == ["E1"]
    assert result["why_it_matters"] == result["uncertainty"] == ""
    with pytest.raises(ValueError, match="requires a cited finding"):
        assess_claims(claim, sources, CONFIG, CompactRunner(lambda data: response([])))


def test_thesis_point_must_be_anchored_in_the_saved_thesis():
    from app.evidence import select_thesis_claims

    thesis = "Backlog should convert next year if supplier lead times normalize."
    ungrounded = Runner(lambda data: {
        "claims": [{"driver": "Margins", "text": "Margins rise", "quotes": ["Operating margin will rise."]}]
    })
    with pytest.raises(ValueError, match="quote the saved thesis"):
        select_thesis_claims(thesis, CONFIG, ungrounded)


def test_call_retrieval_keeps_late_qualified_answers_with_speaker_context():
    from app.evidence import retrieve_call_targets

    turns = [
        {"speaker": "Host", "content": f"Welcome to today's conference, participant {i}."}
        for i in range(80)
    ]
    turns += [
        {"speaker": "Analyst", "role": "analyst", "content": "Did optical terminal orders accelerate?"},
        {"speaker": "CEO", "role": "management", "content": "No. Several customers delayed commitments."},
    ]
    result = retrieve_call_targets(
        {"turns": turns, "source_url": "https://example.com/call"},
        [{"id": "C1", "text": "Optical terminal orders should accelerate."},
         {"id": "C2", "text": "Renewals will improve."}],
        "2026-09-30",
    )

    assert result["coverage"]["total_blocks"] == 82
    assert result["coverage"]["selected_blocks"] == 2
    assert result["coverage"]["by_claim"]["C2"] == []
    answer = result["targets"][-1]
    assert answer["id"] == "T82.1"
    assert answer["speaker"] == "CEO"
    assert answer["period"] == "2026-09-30"
    assert answer["text"].startswith("No.")
    assert answer["context"]["previous"]["speaker"] == "Analyst"
