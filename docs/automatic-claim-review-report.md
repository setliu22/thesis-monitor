# Automatic claim-review implementation report

Local review on 2026-11-19. Branch `feat/thesis-monitor`, based on `649aebd`.
This report describes the uncommitted local work. No commit, push, deployment,
production migration, or live Groq request was made.

## Current behavior

- Watched companies with a saved thesis automatically review newly discovered
  original 10-Q and 10-K filings. Amendments remain available for manual review;
  8-Ks are not automatic triggers.
- Initial import and recovery catch up at most the latest eligible report.
  Discovery stores filings and registers review work before company-facts
  processing finishes. A bounded daily SEC submissions check covers the gap
  between full refreshes.
- Manual requests and automatic work share the same company, filing, captured
  thesis version, model and analysis-version identity. Thesis edits do not start
  historical sweeps. Reruns reuse pinned sources and validated batches.
- Stage A links evidence passages to exact claim IDs, preserving paragraph or
  speaker context. Stage B assesses each claim as supports, challenges, mixed
  or insufficient evidence and validates citations before publishing.
- A filing assessment is saved before call lookup. A matching transcript can be
  added later without repeating completed filing requests. It must have a
  verified fiscal quarter; follow-up defaults to 14 days, with checks every
  6 hours. Narrative review remains in-app; no narrative email alerts were added.
- Refresh progress now reaches 4/4 only after the SEC facts transaction commits.
  The UI and shared progress writer were already present; this change corrects
  the stage/count timing.

The review migration is `d7f31a8b920e_claim_reviews.py`. It adds the durable
review identity and nullable stage identity to existing analyses. No production
database migration was run. Required provider configuration remains
`SEC_USER_AGENT`, `GROQ_API_KEY`, and `ALPHAVANTAGE_API_KEY` for call lookup.
The transcript follow-up defaults are configurable with
`TRANSCRIPT_FOLLOWUP_DAYS` and `TRANSCRIPT_RETRY_HOURS`.

## Muse patch decisions

The patch was not applied wholesale; `git apply --check` fails on overlapping
files. The null-safe SEC mapping code, progress persistence/UI, 10-minute retry
for a never-synced company, error label and thesis placeholder were already in
the worktree. I added null-metadata regression tests and corrected progress
stage timing.

I skipped Muse's age-based stuck-job replacement. It decides a running job is
stale from `available_at`, while the worker renews `lease_until`; a healthy
refresh lasting more than 15 minutes could therefore be failed and replaced.
I also skipped unrelated calendar styling/scoping, economic status labels,
computed stock-effect labels, chart annotations, filings-tab removal and source
link removal. Removing source links conflicts with this review's requirement
to inspect the cited disclosure. Simple macro/company heuristics would also
present inferred market effects as firmer than the stored data supports.

## Verification

- Backend: 132 passed, 3 skipped. The skipped Groq/runtime, refresh-job and
  review concurrency cases require PostgreSQL row locks. SQLite migration and
  legacy-row checks passed as part of the suite.
- Frontend: 21 tests passed; TypeScript/Vite production build passed.
- Focused Ruff undefined-name checks passed. The default Ruff rules report many
  repository-wide style and rule findings, so they are not a clean project-wide
  gate for this work.
- Offline labeled fixtures: 7 cases and 6 evidence anchors. Existing retrieval
  found 4/4 labeled filing anchors; contextual retrieval found 4/4 and call
  retrieval found 2/2. Contextual selection included 5 additional blocks among
  11 selected; those are retrieval extras, not measured classification errors.
  Speaker attribution was checked on one labeled call anchor and matched.
  Classification agreement, false-positive rate and citation accuracy remain
  unmeasured because the fixture harness makes no model calls.
- Offline sizing on separate local CACI inputs: 9 claims, 56 filing targets in
  4 planned Stage A requests (29,794 reserved-token estimate) and 79 call
  targets in 6 planned Stage A requests (43,630 estimate). Provider calls were
  zero. This is not a matched review, does not include Stage B, and is not actual
  token use or latency.

## Still unverified

- No live Groq assessment was run, by request. The model's real claim-level
  accuracy, citation quality, latency and actual free-tier usage are unknown.
- PostgreSQL row-lock concurrency and the migration against a real PostgreSQL
  server were not exercised here. Three PostgreSQL-only tests skipped on SQLite.
- The hosted runner, hosted database and deployed UI were not changed or checked.
- The small synthetic retrieval set does not establish quality across companies
  or filing styles. The CACI request-size profile uses separate local filing and
  call documents and cannot establish a typical per-review cost.

The full application code and migration remain local and uncommitted for review.
