"""Offline held-out retrieval evaluation. No provider calls or production records.
Classification/synthesis metrics intentionally unmeasured without independent outputs.
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.evidence import split_claims, filing_targets, call_targets
from app.retrieval import select_evidence


def evaluate():
    cases = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "backend/evals/claim_evidence_cases.json"
        ).read_text()
    )["held_out"]
    counts = {
        "labeled_evidence": 0,
        "baseline_retrieved": 0,
        "contextual_retrieved": 0,
        "contextual_selected": 0,
        "contextual_incorrectly_included": 0,
        "source_speaker_correct": 0,
        "source_speaker_checked": 0,
        "filing_labeled": 0,
        "filing_baseline_retrieved": 0,
        "filing_contextual_retrieved": 0,
        "call_labeled": 0,
        "call_retrieved": 0,
    }
    details = []
    for case in cases:
        claims = split_claims(case["claim"])
        filing = filing_targets(case.get("filing", ""), claims)["targets"]
        call = call_targets({"turns": case.get("turns", [])})["targets"]
        targets = filing + call
        baseline = select_evidence(case.get("filing", ""), case["claim"])["text"]
        labels = case["evidence"]
        counts["labeled_evidence"] += len(labels)
        matched = []
        for label in labels:
            hits = [
                t for t in targets if label["contains"].lower() in t["text"].lower()
            ]
            counts["contextual_retrieved"] += bool(hits)
            counts["baseline_retrieved"] += (
                label["contains"].lower() in baseline.lower()
            )
            if "speaker" in label:
                counts["source_speaker_checked"] += 1
                counts["source_speaker_correct"] += bool(hits) and all(
                    t.get("speaker") == label["speaker"] for t in hits
                )
            if label["source_type"] == "call":
                counts["call_labeled"] += 1
                counts["call_retrieved"] += any(
                    label["contains"].lower() in t["text"].lower() for t in call
                )
            else:
                counts["filing_labeled"] += 1
                counts["filing_baseline_retrieved"] += (
                    label["contains"].lower() in baseline.lower()
                )
                counts["filing_contextual_retrieved"] += any(
                    label["contains"].lower() in t["text"].lower() for t in filing
                )
            matched.append(bool(hits))
        counts["contextual_selected"] += len(targets)
        counts["contextual_incorrectly_included"] += sum(
            not any(label["contains"].lower() in t["text"].lower() for label in labels)
            for t in targets
        )
        details.append(
            {
                "id": case["id"],
                "retrieved_labels": matched,
                "selected_targets": len(targets),
            }
        )
    return {
        "fixture_cases": len(cases),
        "metrics": counts,
        "filing_baseline_retrieval_recall": counts["filing_baseline_retrieved"]
        / counts["filing_labeled"],
        "filing_contextual_retrieval_recall": counts["filing_contextual_retrieved"]
        / counts["filing_labeled"],
        "call_retrieval_recall": counts["call_retrieved"] / counts["call_labeled"],
        "classification_false_positives": None,
        "synthesis_agreement": None,
        "citation_accuracy": None,
        "requests": 0,
        "provider_tokens": 0,
        "limits": "Tiny held-out sample. Filing recall compares the same filing-only labels; call recall is separate. Evidence source types are independently labeled in the fixture. Nonlabelled selected paragraphs are retrieval extras, not classified false positives. Classification/synthesis/citation metrics require independent model outputs and are not inferred from mocks.",
        "cases": details,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
