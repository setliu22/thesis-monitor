# Investment Thesis Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver a locally runnable CACI-first investment thesis monitor with SEC evidence, configurable rules, background ingestion, and interview documentation.

**Architecture:** React talks to FastAPI; PostgreSQL stores versioned financial data and durable jobs. A separate worker fetches SEC records and evaluates rules. Optional LLM analysis validates evidence against fetched filing text.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL, React, TypeScript, Vite, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-thesis-monitor-design.md`

**Execution status:** Implementation and local verification complete. Live SEC/provider calls and Docker runtime checks remain pending configuration, as recorded in `docs/verification.md`.

## Global Constraints
- Single-user local application; bind local services to localhost.
- No invented financial records or fabricated alerts.
- Core monitoring works without an API key.
- Require a configurable descriptive User-Agent with a real contact address; do not fabricate contact details.
- Throttle conservatively below the SEC maximum of 10 requests/second across this application's workers.
- Failed refreshes retain the last good dataset and mark it stale.
- No network messages are sent as part of setup or verification.
- Preserve source facts, derivation lineage, rule versions, and thesis versions.

## Review Focus
- SEC discovery succeeds before facts arrive: show pending metrics and retry without losing filing metadata (Task 2/3).
- Fiscal years differ from calendar years: compare equivalent durations rather than calendar labels (Task 2).
- Rule edits overlap refresh execution: record and evaluate the specific saved rule version, deduplicating per version (Task 3/4).
- A worker dies while holding a job: recover its expired lease without duplicate alerts (Task 3).
- SEC and LLM content contains hostile instructions or unsupported quotes: render text safely and reject unsupported evidence (Task 5).

## File responsibilities
- `backend/app/config.py`, `db.py`, `models.py`: settings, sessions, durable schema.
- `backend/alembic/`: schema migrations.
- `backend/app/sec.py`: SEC identity, fixed-host fetches, throttling, retry, bounded responses.
- `backend/app/financials.py`: pure period selection, tag mappings, derivations, metric provenance.
- `backend/app/jobs.py`, `ingest.py`, `worker.py`: durable queue, ingestion orchestration, polling/scheduling.
- `backend/app/rules.py`: deterministic evaluation and deduplicated alerts.
- `backend/app/schemas.py`, `main.py`: validated API contracts and HTTP routes.
- `backend/app/analysis.py`: optional LLM request and evidence validation.
- `backend/tests/`: financial, pipeline, job, API, and analysis tests.
- `frontend/src/api.ts`, `types.ts`: typed API boundary.
- `frontend/src/App.tsx`, `components/`, `styles.css`: responsive dashboard and editing workflows.
- `compose.yaml`, Dockerfiles, `.env.example`, `README.md`, `docs/`: runtime and handoff.

### Task 1: Durable application foundation
**Files:** Create backend package/configuration, db/models, Alembic migration, `tests/test_storage.py`, backend Dockerfile, compose database/API services, `.gitignore`, `.env.example`.
**Interfaces:** `Settings` loads DATABASE_URL, SEC_USER_AGENT, refresh interval, optional model credentials; `get_session()` provides SQLAlchemy sessions. Models expose Company, ThesisVersion, RuleVersion, Snapshot, Filing, Fact, Observation, Job, Analysis, Alert, AlertEvent.
- [x] Write storage tests: company ticker uniqueness; thesis/rule revisions remain queryable; filing accession uniqueness; alert dedupe constraint; migration reaches head on empty PostgreSQL database.
- [x] Run targeted tests and confirm failure before implementing the missing schema.
- [x] Implement models with UTC timestamps, explicit numeric precision, foreign keys and unique constraints; create first migration. Use JSON for source payload and provenance, not financial numeric arithmetic.
- [x] Run migration and storage tests; confirm persistence across a session restart and verify secrets are ignored.
- [x] Commit foundation.

### Task 2: SEC client and correct financial normalization
**Files:** Create `sec.py`, `financials.py`, `tests/test_sec.py`, `tests/test_financials.py`, small explicitly synthetic test fixtures.
**Interfaces:** `SecClient.fetch_json(path: str) -> dict`; `resolve_company(ticker: str) -> CompanyIdentity`; `normalize(companyfacts: dict, as_of: datetime) -> list[MetricObservation]`. Observations carry metric, value, unit, start/end, duration kind, source accessions/tags, filed timestamp, derivation, and unavailable reason.
- [x] Write failing tests for missing identity, invalid host/path, timeout/429 behavior, response size limits, and backoff exhaustion.
- [x] Implement fixed SEC endpoint construction, one shared request gate for this worker deployment, descriptive identity validation, timeouts, bounded payloads and Retry-After handling. Keep frontend requests entirely local.
- [x] Write failing financial tests: revenue 120 versus 100 gives 20% growth; income 12/revenue 120 gives 10% margin; compatible YTD 300 minus 190 yields quarter 110; incompatible fiscal years/units/tags cannot derive; zero denominator is unavailable; noncalendar fiscal years compare correctly; amendments honor as-of dates; instant debt does not become a duration; negative cash flow growth has an explicit documented interpretation or is unavailable.
- [x] Implement canonical metric mappings and pure normalization using Decimal, duration-aware selection, explicit provenance and unavailable results. Use only compatible inputs; retain source version identity.
- [x] Run targeted tests. Fetch actual CACI metadata and facts if SEC access is configured; inspect available tags and record mapping decisions. If credentials/access are absent, report setup-needed and defer live verification without fabricated data.
- [x] Commit SEC integration and normalization.

### Task 3: Ingestion, durable jobs, and alerts
**Files:** Create `jobs.py`, `ingest.py`, `rules.py`, `worker.py`, `tests/test_jobs.py`, `tests/test_ingest.py`, `tests/test_rules.py`; add worker service.
**Interfaces:** `enqueue_refresh(session, company_id: int) -> Job`; `claim_job(session, worker_id: str) -> Job | None`; `run_refresh(job_id: int) -> None`; `evaluate_rule(rule: RuleVersion, observations: list[MetricObservation]) -> Evaluation`; `worker.main()` polls, renews leases, and schedules refreshes.
- [x] Write failing tests for duplicate enqueue, competing job claims, expired lease recovery, retry exhaustion, and bounded attempts. Test against PostgreSQL for locking behavior.
- [x] Implement row-lock claims, leases/renewal, bounded retry with exponential backoff, hourly configurable scheduling, and structured job logging.
- [x] Write failing ingestion tests for repeat responses, changed snapshots, partial filing discovery before facts, SEC failure retaining last good data, and reprocessing once delayed facts arrive.
- [x] Implement snapshot hashing, accession-based filing upserts, version-preserving facts/observations, transaction boundaries and pending/stale status.
- [x] Write failing rule tests for each supported operator, unavailable inputs, exact boundaries, revision races, acknowledgment history, and duplicate delivery after worker recovery.
- [x] Implement numeric evaluation with rule-version and observation identity dedupe; store values, thresholds, units, periods and source links in alert evidence. Keep suggested rules disabled until explicitly saved.
- [x] Run queue, ingestion and rule tests; commit worker pipeline.

### Task 4: Validated API and React dashboard
**Files:** Create `schemas.py`, `main.py`, `tests/test_api.py`; frontend package/Vite setup, `api.ts`, `types.ts`, `App.tsx`, `components/CompanyDetail.tsx`, `RuleEditor.tsx`, `AlertFeed.tsx`, `JobStatus.tsx`, `styles.css`; frontend Dockerfile and compose proxy.
**Interfaces:** `/api/companies` list/create; `/api/companies/{id}` detail; versioned thesis/rule writes; `/api/companies/{id}/refresh` queues a job; `/api/companies/{id}/evaluate` evaluates saved rules; `/api/alerts/{id}/acknowledge`; `/api/jobs`; `/health`, `/ready`. Detail response includes history, provenance, availability and freshness.
- [x] Write failing API tests for ticker/rule validation, unknown IDs, thesis revisions, stale data, concurrent refresh dedupe, setup-needed state, and saved-rule evaluation.
- [x] Implement API and serialize Decimal/date values explicitly. Readiness checks database connectivity without making remote calls. Expose actionable errors without secrets.
- [x] Implement responsive watchlist/dashboard, CACI starter onboarding, thesis editor, rule create/edit/disable, trend charts, source details, filing list, alert acknowledgment and refresh/job status. Handle loading, empty, failed and stale states.
- [x] Keep demo thresholds clearly labeled; never create an alert without an evaluated real observation. Poll job progress at a bounded interval and stop polling completed jobs.
- [x] Run API tests and frontend production build. Inspect main browser flows, keyboard access, long company/thesis text, narrow layout and unavailable metrics when browser tooling permits.
- [x] Commit API and UI.

### Task 5: Optional grounded filing analysis
**Files:** Create `analysis.py`, `tests/test_analysis.py`; extend API, worker jobs and UI analysis panel; document optional credentials.
**Interfaces:** `analyze_filing(text: str, thesis: str, config: AnalysisConfig) -> AnalysisResult`; `verify_evidence(result: AnalysisResult, supplied_text: str) -> AnalysisResult`. Store accession, thesis version, model and prompt version.
- [x] Write failing tests for absent key, invalid schema, unsupported quotations, bounded excerpts, provider timeout, hostile filing instructions, and mismatched thesis versions.
- [x] Implement optional server-side model adapter with structured output validation. Exact quotes must exist in supplied normalized text; unsupported observations cannot appear as verified. Treat document instructions as data and give the model no tools.
- [x] Queue analysis explicitly, store reproducibility metadata, and display model observations separately from numeric alerts with source evidence. Show disabled/setup-needed state without credentials.
- [x] Run analysis and API tests using mocked provider responses; make no paid model call unless credentials and scope authorize it. Commit optional analysis.

### Task 6: Reproducibility, end-to-end verification, and interview handoff
**Files:** Complete `README.md`, `docs/architecture.md`, `docs/interview-guide.md`, `docs/demo.md`, `docs/limitations.md`, compose and env example; add CI workflow.
**Interfaces:** Document `docker compose up --build`, migration/startup behavior, test commands and worker operation. Demo uses the same API/UI as ordinary operation.
- [x] Document setup with a real SEC contact address, configured secrets, persistence, reset behavior, troubleshooting, source policies and data limitations.
- [x] Write an interview guide covering the actual decisions, SQL schema, idempotency, failure recovery, period correctness, LLM evidence checks, and honest measurements the user can collect.
- [x] Run backend test suite, frontend production build, migrations and Compose configuration validation. Fix failures before widening checks.
- [x] Run the actual CACI flow when available: resolve ticker, queue fetch, inspect provenance, save thesis/rule, evaluate against real observation, acknowledge resulting alert, repeat ingestion, restart and confirm persistence. Record exactly what was exercised and external blockers.
- [x] Review implementation against every spec acceptance criterion; address actionable findings, update plan checkboxes and commit final deliverables. Report verified results and remaining setup in the final handoff.
