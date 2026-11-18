"""Read a saved thesis and evaluate a real call without changing thesis/analysis records.

Usage: PYTHONPATH=backend .venv/bin/python scripts/evaluate_transcript.py \
  --ticker CACI --quarter 2026Q3 --output work/call-eval.json
"""

import argparse
import json
from pathlib import Path
from sqlalchemy import select
from app.feed_cache import FeedError
from app.analysis import analysis_config
from app.config import settings
from app.db import SessionLocal
from app.models import Company, ThesisVersion
from app.transcripts import fetch_transcript, compare_transcript


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--quarter", required=True)
    parser.add_argument(
        "--expect",
        action="append",
        default=[],
        help="Exact source-text anchor to check; not a general benchmark",
    )
    parser.add_argument("--output", default="work/call-eval.json")
    args = parser.parse_args()
    ticker = args.ticker.upper()
    with SessionLocal() as session:
        company = session.scalar(select(Company).where(Company.ticker == ticker))
        if not company:
            parser.error("Company is not in the application")
        thesis = session.scalar(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(ThesisVersion.version.desc())
        )
        if not thesis:
            parser.error("Save a thesis for this company first")
        body, version = thesis.body, thesis.version
    try:
        source = fetch_transcript(
            ticker, args.quarter, settings.alphavantage_api_key, SessionLocal
        )
        result = compare_transcript(source, body, analysis_config())
    except (ValueError, FeedError) as exc:
        parser.exit(1, str(exc) + "\n")
    checks = {
        anchor: any(anchor in o["quote"] for o in result["observations"])
        for anchor in args.expect
    }
    exact = all(
        o["thesis_quote"] in body
        and any(
            o["speaker"] == t["speaker"] and o["quote"] in t["content"]
            for t in source["turns"]
        )
        for o in result["observations"]
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "ticker": ticker,
                "quarter": args.quarter,
                "thesis_version": version,
                "source_quotes_exact": exact,
                "selected_anchor_checks": checks,
                "result": result,
            },
            indent=2,
        )
    )
    print(
        json.dumps(
            {
                "quarter": args.quarter,
                "coverage": result["coverage"],
                "related_passages": len(result["observations"]),
                "source_quotes_exact": exact,
                "selected_anchor_checks": checks,
            },
            indent=2,
        )
    )
    if not exact or not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
