# Data providers

## Current behavior

- Watchlists start empty. Stocks are resolved using SEC ticker/company records; existing saved stocks remain user data.
- SEC EDGAR supplies filings and companyfacts for every watched issuer using the same code. Numeric metrics use standard US GAAP concepts and compatible reporting periods. Company-specific taxonomy overrides are not supported. An unavailable metric is shown as unavailable; it is never filled using another issuer's assumptions.
- Alpha Vantage supplies expected earnings dates through EARNINGS_CALENDAR with a 12-month horizon. One leased PostgreSQL cache stores the full response, shared by every watchlist ticker. The cache survives restarts. Calendar refresh defaults to 24 hours; adding a ticker reuses the cache.
- Dates are provider estimates, not claimed issuer confirmations. Coverage and access depend on the provider. Missing/invalid dates, a missing key and provider quota/entitlement errors are shown explicitly. No local 91-day estimate or company website scraper remains.
- Provider changes for the same fiscal period update the saved date. A release that has passed remains pending while SEC financial data arrives, even if the next provider response rolls forward. Daily financial refreshes stop after the matching fiscal period's 10-Q/10-K and revenue data exist, or the configured follow-up window ends. This does not monitor every off-cycle amendment.
- New rules have no suggested name or numeric threshold. Choose them yourself.

## Setup

Get a key at https://www.alphavantage.co/support/#api-key and save ALPHAVANTAGE_API_KEY in ignored .env (or hosting secrets). Restart API and SEC worker. A newly added key bypasses the cached missing-key error. No key is present locally yet; the production provider request has not been validated with an account. No provider subscription or spending was authorized.

Configuration: CALENDAR_REFRESH_HOURS, FINANCIAL_REFRESH_HOURS, EARNINGS_LEAD_DAYS and EARNINGS_FOLLOWUP_DAYS. Defaults are 24, 24, 0 and 30 respectively. These are scheduling policy settings, shared by all issuers.

## Retired shortcuts

The November 16 migration clears dates created by issuer scraping or filing-date arithmetic. It deactivates capex and dependent observations that relied on a broad productive-assets tag and an issuer-specific interpretation. Raw source snapshots and historical observations are preserved for audit. As a result, some saved stocks now have unavailable capex/free-cash-flow values; adding a normalized financial-statement provider or a general, evidence-backed taxonomy mapping system is separate work.

Test fixtures and historical design/review records may mention example tickers; runtime code contains no ticker or company-ID conditions. Earlier documents describing CACI-specific scraping or capex behavior are historical and superseded by this document.

Provider documentation: https://www.alphavantage.co/documentation/#earnings-calendar
