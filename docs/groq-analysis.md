# Groq filing analysis

The deployed app uses Groq's chat completions endpoint with strict structured
outputs. The default model is `openai/gpt-oss-20b`, configurable through
`GROQ_MODEL`; choosing another model requires structured-output support.
The model name identifies an open-weight model served by Groq, not an OpenAI
API request. No automatic provider fallback is performed.

Set `GROQ_API_KEY` in the ignored local `.env`, the Render web service environment,
and GitHub Actions repository secrets. `GROQ_MODEL` is an optional GitHub repository
variable; its default matches the backend. Restart local API/worker processes
after changing local environment files. Render must redeploy after secret edits.
The API reports whether a key is present, not whether the provider has quota.

## Use

Save your own thesis under Thesis & rules. Under Filings, select Analyze on a
10-K or 10-Q. The API records a durable analysis job containing the selected
filing and thesis versions. The hosted hourly runner processes it even while
the website sleeps. Results appear in Filing analysis. This remains explicitly
requested analysis; saving a thesis alone does not schedule a comparison, and
this change does not add automatic thesis-change email alerts.

Only selected filing excerpts (up to 8,000 characters) and the first 4,000 thesis
characters are supplied to Groq. The output budget is 4,096 tokens, with low reasoning effort for GPT-OSS models and at most six concise observations. Character
limits reduce usage but do not guarantee compliance with every account's token
quota. The result's scope states these limits; it is not a full-filing review.

The app validates output with Pydantic and discards observations whose supporting
quote is not present within one supplied excerpt. Quote presence establishes
provenance, not the correctness of the model's interpretation. Truncated, refused,
malformed and non-200 responses fail the job without saving partial observations.
Existing bounded job retries apply; provider errors are logged without provider
response bodies or credentials. Stored results identify the provider, requested
model, thesis version, filing accession, excerpt digest and supplied excerpts.

The unused OpenAI adapter and configuration fields have been removed. All model
requests use Groq. The `openai/` model-name prefix and `/openai/v1/` segment in
Groq’s API URL are Groq identifiers, not calls to OpenAI.

## Verification

The CACI failure investigation on November 16, 2026 reproduced completion-token
exhaustion on a full filing request: finish reason `length`, 2,000 completion
tokens, 1,478 of them reasoning tokens. A minimal request using the same strict
schema succeeded. The original HTTP 400 response body was not retained, so its
exact cause cannot be established retrospectively; token exhaustion is the
confirmed reproduced failure, not a proven explanation for that earlier status.

The fix increases the completion budget while reducing input and output bounds.
Provider errors expose only an allowlisted error code, never message prose,
failed generations, credentials, or thesis content. Regression tests cover request
budgets, schema bounds, safe errors, incomplete output rejection, and evidence.
The full backend suite passed: 51 passed, one optional test skipped. Frontend
production build passed. A single controlled CACI analysis using unchanged thesis
version 1 completed and persisted six quote-verified observations (job 8,
analysis 1). This verifies execution and provenance, not investment conclusions.

Tests now clear live provider keys and direct-database overrides. The generic
productive-assets capex fallback was removed; the independently source-verified
CACI definition remains saved in its company-specific mapping registry.

References:
- https://console.groq.com/docs/structured-outputs
- https://console.groq.com/docs/rate-limits

## Concise comparison view

The latest comparison appears before metrics in Overview and before the collapsed
filing archive in Filings. The default verdict is “Analysis needs review” because
model interpretation is not independently validated. At most three year-over-year
changes (revenue, operating margin, operating cash flow) are calculated from
normalized SEC observations for the analyzed filing’s period. Period lengths,
source tags and positive growth denominators must be compatible; margin changes
use percentage points and permit negative or zero prior margins. Every underlying
source for both periods is expandable. No model direction/magnitude is promoted
to this calculated summary.

Raw model observations, assessment labels, quotations and filing links remain in
collapsed evidence, explicitly marked unverified. Older comparisons and the full
filing archive are optional details. New analyses persist `review_status=unverified`.
The existing CACI analysis is retained as `needs_review` with explicit warnings
about the cash-flow direction and relative cost-growth errors; it was not silently
corrected or represented as a trustworthy verdict. The saved thesis is unchanged.

## Thesis passage selection (v3)

The full filing's visible text is scanned in overlapping chunks. Hidden inline
XBRL headers are excluded. Lexical ranking uses the saved thesis, with each claim
getting a selection turn before filling the 8,000-character passage budget. Source
chunk offsets and retrieval version are saved with the analysis. This is bounded
retrieval, not a claim that Groq semantically reads every word of the filing.

The model selects from enumerated passage IDs and thesis-claim IDs. New selections use only related/unclear relevance labels, not supports/challenges investment verdicts. Code attaches
the original text and checks it against both supplied inputs; the model does not
transcribe quotations. Relevance, support/challenge classification, and explanations
remain unverified. Numeric trend claims from tables are disallowed by the prompt;
Overview continues to use independently calculated SEC changes.

Reproduce the small labeled evaluation without provider calls:

```sh
PYTHONPATH=backend .venv/bin/python scripts/evaluate_thesis_passages.py
```

Add `--live --variant revised` to make three bounded Groq checks when real-file
arguments are supplied (two synthetic cases and one public filing). Optional
`--real-html PATH --real-thesis PATH` adds the CACI-style real-document case.
`--case ID` selects one case. Results are saved under ignored `work/` by default.
The benchmark measures labeled-anchor retrieval and extraction recall, plus a
negative-case check. It is a small smoke evaluation, not a general accuracy claim;
returned passages outside the labeled anchor set can still be relevant.

The final live smoke run used a 177,795-character synthetic report, an unrelated
63,620-character adversarial report, and a 265,215-character CACI FY2026 10-K.
The revised retriever included both synthetic targets and all three labeled CACI
anchors; the old retriever included none of the CACI anchors. Groq extracted both
synthetic targets, returned nothing for the unrelated case, and returned five
exact-source notes for CACI. Those notes covered one of the three pre-labeled
anchors (twice with different thesis links); other returned notes can be relevant
but do not count as labeled-anchor hits. Two target passages were not extracted.
Thus source copying and retrieval improved, but extraction recall remains limited.
The baseline prompt's real-document live call failed with json_validate_failed,
so it has no comparable extraction score. Earlier iterations and failure cases
are retained in ignored work outputs; no live results were written over the saved
thesis or existing application analyses.
