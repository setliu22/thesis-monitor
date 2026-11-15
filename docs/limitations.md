# Limitations

- Source scope is public SEC submission metadata, periodic-report US-GAAP XBRL facts, and optional filing text. The app has no stock-price feed, brokerage data, news, analyst estimates, portfolio P&L, or trading features.
- CACI is the starter company; detailed issuer-specific tag coverage still requires real-data review. An SEC contact identity is required before live ingestion. Network access may be blocked independently of that identity.
- Submissions ingestion uses the endpoint's recent filings section. It does not recursively backfill all historical submissions archives. Companyfacts supplies the financial history available from that endpoint.
- US-GAAP mappings are intentionally explicit and limited. IFRS, dimensional segment metrics, custom backlog tags, acquisitions adjustments and issuer-specific non-GAAP measures are unsupported in numeric rules.
- Quarter selection uses duration windows. Nonstandard fiscal transitions, unusual accounting calendars, inconsistent tags, reclassifications and restatements can require manual review. Matching tags/dates do not independently establish identical accounting policy.
- Latest values use filed-date availability, not intraday publication time. Raw snapshots and older normalized versions remain in storage, but the UI shows the current normalized view. There is no point-in-time backtesting interface.
- Negative or zero prior values make percentage growth unavailable. Debt refers to supported long-term-debt totals/components including current maturities, not total liabilities or net debt. Free cash flow uses operating cash flow less available property/plant/equipment expenditure facts.
- Numeric rules inspect the most recent available observation of their selected metric and period kind. Dates are exposed on each metric; an older available metric must not be assumed to belong to a newer filing.
- A valid quote only proves those words occur in the supplied excerpts. Model interpretation can still be wrong. Excerpt selection is bounded and may miss a material disclosure. Analysis is on demand, requires provider credentials, and can incur charges.
- SEC throttling is shared across this deployment's API/worker through its database. Other applications and machines sharing your IP are outside that budget. Long retry delays are surfaced as errors for durable retry.
- Jobs execute at least once. Filing, observation and alert writes are idempotent. A repeated model request after a worker crash can incur a repeated provider charge even when its stored result is deduplicated.
- Alerts are in-app only and appear while using the app. The worker must remain running for scheduled checks. There is no guaranteed delivery SLA, backup policy, retention policy, login, or multi-user isolation.
- Docker Compose is the delivery path. If Docker is unavailable during development, direct PostgreSQL/API/frontend checks do not prove the container images themselves ran; see the verification record.
