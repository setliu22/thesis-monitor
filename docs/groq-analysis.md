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

The previous OpenAI adapter remains callable internally for compatibility with
older direct callers. Application routes and workers use Groq exclusively.

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
