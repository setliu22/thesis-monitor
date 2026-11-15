# Investment Thesis Monitor — proposed design

## Purpose and agreed direction
Build a complete, locally runnable project the user can use to monitor US stocks and explain in FDE interviews. CACI is the first company. The user selected a full-stack application with Python/FastAPI, PostgreSQL, React, and a background worker over Streamlit or an email-only monitor. This design still requires user approval before implementation.

## Goals
- Add US tickers to a persistent watchlist, starting with CACI; write and edit an investment thesis and measurable rules for each company.
- Fetch actual SEC submission metadata and XBRL financial facts; show financial changes with period labels and links to source filings.
- Evaluate configurable numeric rules, generate persistent alerts, and optionally analyze filing text with an LLM using verifiable quotations.
- Run scheduled ingestion outside HTTP requests; expose job progress, failures, retry state, and data freshness.
- Deliver reproducible setup, meaningful tests, architecture documentation, an interview walkthrough, and a demo procedure grounded in real fetched data.

## Boundaries
Single-user local application. No brokerage connection, trading, market-price feed, portfolio performance calculation, authentication, or hosted deployment in version one. Bind local services to localhost. A public deployment requires authentication as a separate change. No invented financial records or fabricated alerts; offline mode may replay a captured SEC response only when its source and capture timestamp are visible.

## Approaches considered
1. Full stack: selected by the user. React dashboard, FastAPI API, PostgreSQL storage, separate worker. More setup, but makes integration, pipeline, database, UI, and reliability decisions tangible.
2. Streamlit: fewer moving parts and quicker initial UI, with less API and frontend depth.
3. Scheduled email monitor: useful for unattended alerts, but offers a smaller interactive interview demonstration.

## Proposed product flow
The user opens a dashboard showing the watchlist, freshness, recent alerts, and ingestion state. Selecting CACI opens the thesis, metric trends, rules, and recent 10-K/10-Q/8-K filings. The user adds a ticker, edits the thesis, and adds or disables threshold rules. Refresh queues a job and returns immediately. Alerts explain the actual value, comparison period, configured threshold, and source. Alerts can be acknowledged. Rule edits can be evaluated immediately against stored data, with the rule version recorded.

Initial CACI rule templates are clearly marked suggestions, disabled until saved by the user: revenue growth below a chosen percentage, operating margin below a chosen percentage, and operating cash flow declining year over year. Debt and capital expenditures are available when normalized data exists. These are monitoring preferences, not claims about the user's investment thesis.

## Data and financial correctness
Use SEC ticker/CIK mapping, company submissions, and companyfacts endpoints. Store raw responses with retrieval time and content hash, normalized facts, filing accession, form, filed date, period start/end, taxonomy tag, unit, and derivation lineage. Preserve original facts when amended filings arrive.

Prefer structured US-GAAP facts for financial numbers. Select annual facts and comparable discrete quarters using duration and fiscal periods, not filing calendar year. Derive a quarter from compatible year-to-date values only when the inputs share fiscal year, unit, and accounting basis; label derived values and retain both inputs. Never compare year-to-date cash flow with a standalone quarter. Use matching prior-year duration for growth. Preserve restatement versions and use the latest filed facts available at each evaluation time. Do not combine incompatible tag definitions silently. Ambiguous or unavailable metrics display 'unavailable' with a reason and cannot trigger a numeric alert.

Support canonical mappings for revenue, operating income, operating cash flow, capital expenditures, and debt with explicit fallback priorities. Operating margin = operating income / revenue for the same duration. Free cash flow = operating cash flow minus capital expenditures for compatible durations. Zero denominators produce unavailable values. Metric history and alert evidence expose source tags and periods.

## LLM analysis
Core monitoring works without an API key. Optional server-side LLM integration analyzes bounded text excerpts from real filings against the saved thesis, returning structured observations with exact supporting quotes and source links. Validate quotations against the supplied text; reject unsupported quotes. Clearly label model observations and keep them distinct from deterministic threshold alerts. Treat filing text as untrusted content. Store model identifier, prompt version, thesis version, and analyzed accession for reproducibility. Do not claim custom concepts such as backlog are covered by standard companyfacts; extract them from filing text only when evidence supports them. No network messages are sent as part of setup or verification.

## Architecture and persistence
React/TypeScript UI talks to FastAPI through a local development proxy. PostgreSQL is the shared durable store. SQLAlchemy models and Alembic migrations manage companies, thesis versions, rule versions, raw snapshots, filings, facts, metric observations, jobs, analyses, alerts, and alert events. A separate Python worker polls durable jobs using database row locks, leases, bounded retries, and exponential backoff. It schedules periodic company refreshes, initially hourly and configurable. Avoid Redis/Celery in this first version to keep operations manageable. Docker Compose provides the primary one-command runtime; document local development separately.

Jobs have queued/running/succeeded/failed states, attempt counts, last error, lease expiry, and timestamps. Recover abandoned leases after a worker crash. Deduplicate refresh requests per company. Ingestion upserts by stable source identifiers. Alerts deduplicate by rule version and observation/filing identity so retries do not spam the feed. Failed refreshes retain the last good dataset and mark it stale; filing discovery can succeed while facts remain pending. A later refresh retries incomplete financial processing.

## SEC access and operational behavior
All SEC requests run server-side. Require a configurable descriptive User-Agent with a real contact address; do not fabricate contact details. Throttle conservatively below the SEC maximum of 10 requests/second across this application's workers. Honor 429/Retry-After, back off on transient failures, set timeouts, and bound response size. Validate tickers through the mapping and restrict remote fetches to known SEC hosts and constructed SEC paths. Display setup-needed state if the SEC identity is absent and explicit errors if access is blocked.

Secrets stay in environment variables, never browser bundles or tracked files. Validate rule operators, thresholds, metric names, and company identifiers. Render extracted content as text. Use parameterized ORM queries. Provide health/readiness endpoints and structured logs with job and company identifiers.

## Delivery and acceptance
A clean checkout starts via documented Docker Compose commands after setting SEC_USER_AGENT. The browser can add CACI, fetch real data, save a thesis and numeric rule, queue a refresh, inspect correctly labeled metrics, and review evidence for an alert when its threshold is met. No guaranteed alert is manufactured; the demo can configure a clearly identified demonstration threshold against a real observation. Restarting services retains records. Duplicate ingestion does not duplicate filings or alerts. SEC failures appear in job history and preserve previous data. Optional LLM mode has an explicit disabled state without credentials.

Test period normalization, YTD-to-quarter derivation, unsupported facts, zero denominators, rule evaluation, idempotency, lease recovery, API validation, and quote verification. Use small synthetic financial fixtures clearly confined to tests; integration verification should capture or fetch genuine SEC records. Verify frontend production build and the main UI flow where the runtime permits. Report any unverified portions explicitly.

Include README setup/troubleshooting, environment example, API usage, architecture and tradeoffs, data limitations, and an interview guide covering problem discovery, SEC constraints, SQL design, reliability, LLM evaluation, and honest project outcomes. No invented users, production scale, or impact measurements.

## Builder decisions
The builder may choose maintained package versions, UI styling, chart library, exact endpoint shapes, database indexes, specific retry intervals, and the optional LLM provider/model. Record significant decisions in documentation. The builder must inspect actual CACI facts before settling tag mappings and must not promise unsupported metrics.

## Sources
- SEC public data APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC access policy and identity: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- SEC developer resources and rate guidance: https://www.sec.gov/about/developer-resources
