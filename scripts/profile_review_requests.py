"""Plan evidence-stage requests offline. Never calls a model or edits app records."""

import argparse
import json
import time
from pathlib import Path
from types import SimpleNamespace
from app.evidence import split_claims, filing_targets, call_targets, find_evidence
from app.groq_runtime import Limits, estimate


class Planner:
    limits = Limits()

    def __init__(self):
        self.requests = 0
        self.reserved = 0

    def __call__(self, body, validate):
        self.requests += 1
        self.reserved += estimate(body)
        data = json.loads(body["messages"][1]["content"])
        raw = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "decisions": [
                                    {"target_id": t["id"], "links": []}
                                    for t in data["targets"]
                                ]
                            }
                        )
                    },
                }
            ]
        }
        validate(raw)
        return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thesis", required=True)
    parser.add_argument("--filing-html", required=True)
    parser.add_argument("--transcript", required=True)
    args = parser.parse_args()
    start = time.perf_counter()
    claims = split_claims(Path(args.thesis).read_text())
    sources = {
        "filing": filing_targets(Path(args.filing_html).read_text(), claims),
        "call": call_targets(json.loads(Path(args.transcript).read_text())),
    }
    rows = {}
    for name, source in sources.items():
        plan = Planner()
        find_evidence(source, claims, SimpleNamespace(model="openai/gpt-oss-20b"), plan)
        rows[name] = {
            "targets": len(source["targets"]),
            "planned_requests": plan.requests,
            "reserved_token_upper_bound": plan.reserved,
        }
    print(
        json.dumps(
            {
                "claims": len(claims),
                "stage_a_only": True,
                "sources": rows,
                "provider_requests": 0,
                "actual_provider_tokens": None,
                "elapsed_local_seconds": round(time.perf_counter() - start, 3),
                "limits": "Separate local documents used for request sizing; not a matched earnings review or model quality evaluation. Synthesis and late-call probes add work; model usage and latency are unmeasured.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
