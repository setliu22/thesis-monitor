# Groq thesis reviews

This page describes the implementation in the current local branch. It has not
been deployed; the hosted app remains on its previous version until the review
migration and application are released.

The app uses Groq's chat completions endpoint with strict structured
outputs. The default model is `openai/gpt-oss-20b`, configurable through
`GROQ_MODEL`; choosing another model requires structured-output support.
The model name identifies an open-weight model served by Groq, not an OpenAI
API request. No automatic provider fallback is performed.

Set `GROQ_API_KEY` in the ignored local `.env`. Restart the local app after changing it.
The API reports whether a key is present, not whether the provider has quota.

## Local model evaluation

`scripts/evaluate_local_review.py` compares keyword retrieval with keyword plus
MiniLM retrieval, then runs the same evidence and citation validators against
a local Qwen GGUF through `llama-server`. It reports the expected and actual
verdict, labeled passage and citation matches, request count, tokens, and time
for each case. The evaluation uses local model files and does not change saved
reviews.

Create a separate virtual environment with the backend requirements and
`sentence-transformers`. With `llama-server` on your path, run:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python scripts/evaluate_local_review.py \
  --model /path/to/qwen.gguf --embedding-model /path/to/minilm/snapshot
```

To evaluate additional reports, use `--cases` with a labeled JSON fixture.
A case can use `filing_path` relative to the fixture for a saved HTML filing.
`--retrieve-only` compares retrieval without starting Qwen.

## Current workflow

Save a thesis for a watched company. The first import is treated as a baseline;
the app catches up only the latest eligible filing. Afterward, each newly
discovered original 10-Q or 10-K is registered for review when a thesis and
Groq key are available. The same service handles deliberate historical reviews
and reruns. Editing a thesis does not launch a historical sweep. Amendments are
manual; 8-K filings are not automatic triggers.

Review identity captures company, filing, thesis version, model and analysis
version. Validated batches and immutable filing/call snapshots are reused after
restarts. Filing evidence is assessed first and published without waiting for a
call. A later matching transcript adds a second result without re-reading the
filing. Fiscal quarter must be verified from the filing; call checks stop after
14 days and retry every 6 hours by default. `TRANSCRIPT_FOLLOWUP_DAYS` and
`TRANSCRIPT_RETRY_HOURS` can change those defaults.

Stage A makes a decision for each selected filing passage or transcript block,
linking it to exact saved claim IDs and a direction. Stage B assesses each claim
as supports, challenges, mixed or insufficient evidence. Code validates claim
and evidence IDs, citations, speaker/source scope and required evidence on both
sides of a mixed assessment. The page shows selective filing coverage and call
coverage separately. Citations open saved source text on demand; source contents
are excluded from polling responses and logs.

Discovery runs during SEC refresh and through a submissions-only daily fallback.
The fallback is bounded and round-robin; hosted scheduled work can wait until
its next runner invocation. Groq quota waits retain the job without consuming
provider-error retries. Narrative reviews stay in the app; no new narrative
email alerts are enabled. The default model is `openai/gpt-oss-20b`, served by
Groq; the prefix does not mean requests go to OpenAI.

Results are model interpretations of cited disclosures. A citation establishes
where a passage came from, not whether the source is true or the interpretation
is correct. Filing retrieval is selective, not a claim that every filing line
was read. See the implementation report for measured checks and limits.

The unused OpenAI adapter and configuration fields have been removed. All model
requests use Groq. The `openai/` model-name prefix and `/openai/v1/` segment in
Groq’s API URL are Groq identifiers, not calls to OpenAI.

## Earlier engine evaluations

The dated version notes below record earlier passage-matching implementations;
they are historical, not measurements of the current claim-review stages.

### Prior Groq filing analysis

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

## Complete passage review (v4)

The top-six selection step has been replaced with explicit relevance classification
of every retrieved passage. Each batch contains at most 48 passages, and the
structured schema requires one claim ID or null per passage ID. Code validates
exact ID coverage before accepting a batch. Later-batch failure rejects the whole
analysis; partial results are not saved. There are at most 192 passages and four
batches. Bounded 429 retries honor short Retry-After values; no provider prose or
private payloads are included in errors.

This removes highlight selection as a source of omissions and avoids generated
explanations. Source text and thesis clauses are attached by code. All decisions,
source units, claim units, and coverage counts are retained for audit. Relevance
still comes from the model and is not a thesis-impact verdict. Narrative text is
now prominent in new comparisons; numeric changes and the full matched set remain
expandable. Old matches are not promoted after the saved thesis changes.

On identical CACI excerpts, the v3 selection prompt returned 2/3 labeled anchors
with 20B and 0/3 with 120B in the comparison run. With v4, both returned 3/3.
The final 20B smoke run recovered 3/3 real anchors and 2/2 synthetic anchors,
with no retained notes for the unrelated/adversarial case (one model selection was
rejected by the instruction-pattern check). This is still a small development
sample, not a general accuracy guarantee. Keep 20B as default; the larger model
was unnecessary on this case. `--model openai/gpt-oss-120b` allows reproducing
model comparisons without changing application settings.

The application end-to-end check saved analysis 2 from CACI's actual FY2026 10-K:
49/49 selected passages classified in two batches, 17 source-backed matches, all
three labeled anchors recovered. Thesis version 1 and its text were unchanged.
The prompt identifier is `v4-passage-review` to fit the existing VARCHAR(20).
A regression test now enforces that field limit. Database job errors are sanitized
rather than exposing SQL parameters in the UI.

### Local hybrid retrieval

New filing and earnings call selections combine keyword ranking and local
MiniLM similarity using reciprocal rank fusion. Source passage vectors are cached
separately from thesis queries under `work/embedding-cache/`, so thesis edits do
not require re-encoding unchanged documents. Saved selections and reviews remain
reusable. Retrieval preserves the original passage IDs and source metadata.

The worker defaults to the evaluation Python environment at
`work/local-model-eval-venv/bin/python` and the locally cached
`sentence-transformers/all-MiniLM-L6-v2` model. Set `THESIS_EMBEDDING_PYTHON`
to a Python executable with `sentence-transformers` installed, or
`THESIS_EMBEDDING_MODEL` to a local model snapshot, to override those defaults.
The encoder runs offline. If it is unavailable, the worker logs the fallback and
records keyword-only retrieval in coverage metadata.
