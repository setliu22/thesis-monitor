# Earnings-call evaluation — November 18, 2026

Tested real fiscal 2025 Q4 transcripts from Alpha Vantage using Groq-served `openai/gpt-oss-20b`. The five companies span software, semiconductors, banking, retail and energy. Fiscal quarters do not necessarily share calendar dates. Sample theses were used; no watchlist entry, invested status, saved thesis or application analysis was changed.

| Company | Selected passages classified | Preselected passages found | Correct thesis links on those targets | Unrelated-thesis matches |
|---|---:|---:|---:|---:|
| MSFT | 50 | 3/3 | 3/3 | 0 |
| NVDA | 64 | 3/3 | 3/3 | 0 |
| JPM | 46 | 3/3 | 3/3 | 0 |
| COST | 46 | 2/3 | 2/3 | 0 |
| XOM | 54 | 3/3 | 3/3 | 0 |

Across the five calls, Groq classified all 260 selected passages. It found 14/15 preselected passages and linked 14/15 to the expected thesis sentence. All returned source quotes, thesis quotes and speaker attributions matched the supplied data. The same 260 passages were separately classified against an unrelated veterinary-vaccine thesis, producing 0 matches.

## What was checked

- Microsoft: cloud demand, capacity constraints and Copilot adoption.
- NVIDIA: Blackwell sales, inference demand and China export exposure.
- JPMorgan: rates/deposit balances, credit-card losses and investment-banking fees.
- Costco: membership income, annual warehouse openings and e-commerce sales.
- ExxonMobil: Guyana/Permian production, LNG projects and cost savings.

## The missed passage

Costco’s specific annual warehouse-opening count was excluded by the 8,000-character retrieval budget and never reached Groq. Other warehouse-expansion discussion was retrieved and returned, including planned openings and the effect of additional warehouses on sales. The preselected annual-count check remains marked as a failure.

## Limits

This is a small exploratory evaluation with manually chosen source anchors, not a blind precision/recall benchmark. The checks do not label every potentially relevant sentence or validate every returned interpretation. The unrelated-thesis control is a basic rejection check, not a measurement of false positives on subtle claims. Exact quotation establishes provenance; it does not establish that management’s statements are true or that an investment thesis is correct. The pipeline classifies selected excerpts rather than reviewing every sentence semantically.

Alpha Vantage briefly rate-limited burst requests during download; the five successful source payloads were retained locally. Groq token limits required spacing positive and negative runs. Raw calls and full model responses stay in ignored `work/transcript-suite/`. No runtime application code changed for this evaluation.

## Reproduce

Case definitions: `backend/evals/transcript_cases.json`. Harness: `scripts/evaluate_transcript_suite.py`. Supply the five saved provider payloads in the source directory, then run:

```sh
PYTHONPATH=backend .venv/bin/python scripts/evaluate_transcript_suite.py \
  --live --source-dir work/transcript-suite \
  --output work/transcript-suite/results.json
```

The harness exits with a failure when a required anchor, thesis link, attribution, complete classification, or unrelated-thesis check fails. The Costco miss means this dataset is not an all-green benchmark.
