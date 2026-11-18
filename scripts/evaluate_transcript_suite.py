"""Evaluate saved real call payloads against labeled sample theses; no portfolio writes.

--source-dir contains TICKER.json payloads returned by app.transcripts.fetch_transcript.
--live sends selected passages to Groq. Source files stay outside version control.
"""

import argparse
import json
import hashlib
import time
from pathlib import Path
from app.analysis import (
    analyze_filing,
    analysis_config,
    text_units,
    PROMPT_VERSION,
    ANALYSIS_PROMPT,
)
from app.transcripts import compare_transcript, select_transcript_evidence


def evaluate(
    case, source, config, negative_thesis, checkpoint_dir, pause_seconds, mode="full"
):
    if (source.get("symbol"), source.get("quarter")) != (
        case["ticker"],
        case["quarter"],
    ):
        raise ValueError("Source identity does not match the evaluation case")
    # Confirm labels really exist in this source before running Groq.
    for target in case["targets"]:
        if not any(target["anchor"] in t["content"] for t in source["turns"]):
            raise ValueError("Labeled anchor is absent from source: " + target["name"])
    checkpoint = checkpoint_dir / (case["ticker"] + "-positive.json")
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "case": case,
                "source": source,
                "model": config.model,
                "prompt_version": PROMPT_VERSION,
                "prompt": ANALYSIS_PROMPT,
                "mode": mode,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cached = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    if cached.get("evaluation_fingerprint") == fingerprint:
        result = cached
    else:
        print(case["ticker"] + ": comparing real transcript", flush=True)
        if mode == "full":
            result = compare_transcript(source, case["thesis"], config)
        else:
            selected = select_transcript_evidence(source["turns"], case["thesis"])
            result = analyze_filing(selected["text"], case["thesis"], config)
            for note in result["observations"]:
                passage = next(
                    p for p in selected["passages"] if p["text"] == note["quote"]
                )
                note["speaker"] = passage["speaker"]
            result["supplied_excerpts"] = selected["text"]
        result["evaluation_fingerprint"] = fingerprint
        checkpoint.write_text(json.dumps(result, indent=2))
    print(
        case["ticker"] + ": positive comparison saved; waiting for token allowance",
        flush=True,
    )
    time.sleep(pause_seconds)
    claims = {i + 1: c["text"] for i, c in enumerate(text_units(case["thesis"], "T"))}
    checks = []
    for target in case["targets"]:
        matches = [o for o in result["observations"] if target["anchor"] in o["quote"]]
        checks.append(
            target
            | {
                "retrieved": target["anchor"] in result["supplied_excerpts"],
                "returned": bool(matches),
                "correct_claim": any(
                    o["thesis_quote"] == claims[target["claim"]] for o in matches
                ),
            }
        )
    exact = all(
        o["thesis_quote"] in case["thesis"]
        and any(
            o["speaker"] == t["speaker"] and o["quote"] in t["content"]
            for t in source["turns"]
        )
        for o in result["observations"]
    )
    # Feed identical selected real passages to the classifier with an unrelated
    # thesis, bypassing retrieval so the negative control cannot trivially pass
    # by selecting no passages. This isolates the shared relevance classifier.
    negative = (
        compare_transcript(source, negative_thesis, config)
        if mode == "full"
        else analyze_filing(result["supplied_excerpts"], negative_thesis, config)
    )
    return {
        "ticker": case["ticker"],
        "quarter": case["quarter"],
        "speaker_turns": len(source["turns"]),
        "coverage": result["coverage"],
        "related_passages": len(result["observations"]),
        "source_and_speaker_exact": exact,
        "targets": checks,
        "negative_control": {
            "passages_classified": negative["coverage"]["passages_classified"],
            "unrelated_matches": len(negative["observations"]),
        },
        "result": result,
        "negative_result": negative,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="backend/evals/transcript_cases.json")
    parser.add_argument("--source-dir", default="work/transcript-suite")
    parser.add_argument("--output", default="work/transcript-suite/results.json")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--mode", choices=["full", "excerpt"], default="full")
    parser.add_argument("--pause-seconds", type=float, default=40)
    args = parser.parse_args()
    spec = json.loads(Path(args.cases).read_text())
    if not args.live:
        parser.error("Pass --live to authorize Groq evaluation requests")
    results = []
    for index, case in enumerate(spec["cases"]):
        if index:
            time.sleep(max(0, args.pause_seconds))
        source = json.loads(
            (Path(args.source_dir) / (case["ticker"] + ".json")).read_text()
        )
        result = evaluate(
            case,
            source,
            analysis_config(),
            spec["negative_thesis"],
            Path(args.source_dir),
            max(0, args.pause_seconds),
            args.mode,
        )
        results.append(result)
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"description": spec["description"], "results": results}, indent=2
            )
        )
        print(
            json.dumps(
                {
                    k: v
                    for k, v in result.items()
                    if k not in ("result", "negative_result")
                }
            ),
            flush=True,
        )
    print("Completed", len(results), "companies", flush=True)
    passed = all(
        row["source_and_speaker_exact"]
        and row["coverage"]["passages_considered"]
        == row["coverage"]["passages_classified"]
        and all(
            t["retrieved"] and t["returned"] and t["correct_claim"]
            for t in row["targets"]
        )
        and row["negative_control"]["unrelated_matches"] == 0
        for row in results
    )
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    from app.groq_runtime import Deferred

    try:
        main()
    except Deferred as exc:
        print(
            f"Quota wait: rerun after {exc.delay} seconds. Validated model batches are saved.",
            flush=True,
        )
        raise SystemExit(75)
