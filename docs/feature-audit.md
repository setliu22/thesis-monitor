# Feature audit — November 15, 2026

The application covers the agreed SEC-backed numeric monitor. The full narrative filing-to-thesis workflow is not operational: the optional LLM adapter has no configured provider key and runs on demand, not automatically for each new filing. Earlier delivery language overstated completeness.

| Requested capability | Status | Evidence / remaining work |
|---|---|---|
| Follow US stocks, starting with CACI | Working | CACI submissions and companyfacts fetched from SEC; ticker lookup and watchlist are implemented. |
| Monitor new SEC filings | Implemented and tested | Background worker schedules hourly refreshes and discovers filing accessions. Actual CACI refreshes succeed. A genuinely new filing arriving during a future scheduled cycle has not yet been observed in use. |
| Extract financial changes | Working for supported metrics | Quarterly and annual normalization, year-over-year comparisons and filing provenance. CACI now exposes 15 metrics and 1,150 observations. Capex was checked against the actual cash-flow statement. |
| Show usable financial history | Expanded after audit | Twelve summary cards, selectable metric chart, quarterly/annual table, balance-sheet table, 8/16/all period selection and source inspection. |
| Save and edit an investment thesis | Working | Versioned editor and SQL persistence. The user still needs to enter their actual thesis; the application cannot infer it from owning CACI. |
| Compare results against measurable thesis conditions | Working | Versioned numeric rules, period selection and deterministic evaluation. Verified using genuine SEC snapshots in an isolated database; no claim that a test threshold reflects the user's investment view. |
| Compare narrative disclosures against free-text thesis using an LLM | Not operational | Adapter, schema and quote verification implemented and unit-tested. Requires a provider API key; no live model request or quality evaluation completed. Analysis currently runs only when explicitly requested. |
| Alert when a monitored condition changes | Working for numeric rules | In-app alerts record actual value, threshold, rule version and sources; acknowledgment and dedupe verified with genuine captured SEC data. No email/SMS delivery in the agreed first version. |
| Background jobs, SQL and monitoring | Working locally | PostgreSQL, durable claims/leases/retries, worker logs, job history and freshness indicators. PostgreSQL restart persistence verified. |
| Reproducible complete project / interview material | Delivered with verification limits | Source, migrations, setup, tests, CI configuration, demo and interview guide. Compose config validated; container image build/startup still unverified without a Docker runtime. |

## What was corrected in this audit

- The original dashboard exposed four metrics despite storing hundreds of values. It now exposes income, cash-flow and balance-sheet history.
- CACI's consolidated cash-flow statement uses `PaymentsToAcquireProductiveAssets` for the row labeled **Capital expenditures**. Added an issuer-specific mapping instead of using that broader tag for every company.
- Added net income, diluted EPS, cash/equivalents, assets, liabilities and equity. EPS preserves USD/share units and is never derived by subtracting YTD EPS because weighted share counts can change.
- CACI's latest equity includes noncontrolling interest; source tags and dates remain visible.
- The isolated alert check is recorded in [checks/live-alert-pipeline.json](checks/live-alert-pipeline.json). Its 100% growth threshold is explicitly a verification condition, not a personal thesis or investment alert.

## Still needed before claiming the full original workflow is finished

1. Connect a model provider key and run the filing-to-thesis analysis against genuine filings.
2. Evaluate narrative output against a small labeled set of disclosures, including missed changes and unsupported interpretations.
3. If unattended narrative comparison is required, add explicit automatic-analysis scheduling and a cost limit. The current implementation only schedules numeric monitoring automatically.
4. Verify the Docker runtime path on a machine with Docker installed.

The user also needs to enter their own thesis and enable their chosen thresholds before this can monitor their investment reasoning. That is product setup, not something the app should invent.

### Hosting/email update

Email outbox and separate dispatcher are now implemented with bounded retries, crash recovery, provider idempotency, and visible failure states. Hosted single-owner password protection and a paid Render Blueprint are prepared. **Not activated:** no connected host, verified sender or Resend API key. There is still no running cloud service, no confirmed inbox delivery, no bounce tracking, and no external uptime monitor. See hosting-and-email.md for exact behavior and activation steps; earlier statements that external delivery code is absent are superseded by this update.
