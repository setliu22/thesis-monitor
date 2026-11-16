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

Only selected filing excerpts (up to 12,000 characters) and the first 4,000 thesis
characters are supplied to Groq. The output budget is 2,000 tokens. Character
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

Basic Python lint, compilation and frontend build are checked during implementation.
A read-only review found no important defects. No automated tests were added or
run. Listing models verifies credentials and model availability; it does not
establish analysis quality. A real thesis and a requested filing analysis are
needed to check the complete user flow.

References:
- https://console.groq.com/docs/structured-outputs
- https://console.groq.com/docs/rate-limits
