# Verification record

Verified locally on November 14, 2026 (America/New_York). This record distinguishes deterministic checks from external integrations that still need user configuration.

## Executed

- **35 backend tests passed** against a separate PostgreSQL 16.4 database: storage, financial normalization, SEC transport behavior, durable jobs, replay, lease recovery, actual SKIP LOCKED behavior, rule evaluation, API validation, local-origin protection, optional analysis boundary, and migration upgrade tests.
- **4 frontend workflow tests passed**: empty-data/setup state, thesis save, failed rule-save draft preservation, and idle discovery of scheduled alerts.
- TypeScript check and Vite production build.
- PostgreSQL server restart followed by an actual API read: saved demo thesis and paused rule remained persisted.
- Alembic initial migration and subsequent schema upgrade on a genuine PostgreSQL database.
- Browser preview against the actual API/database: mobile layout, thesis save, and paused-rule save. The preview's thesis/rule are clearly marked demo records used to exercise editing; no financial data or alerts were invented.
- Compose configuration validated with the official standalone Compose v5.7.1 binary (`config --quiet`), downloaded into ignored workspace tools and checksum-verified. Container startup remains unverified without a Docker runtime.

## External checks pending

- Live SEC submissions and companyfacts fetches succeeded on November 15, 2026 after the user supplied a contact identity. Two refresh jobs completed, 60 recent filing records were returned by the UI API, and the browser displayed CACI quarterly revenue, growth, and operating margin for September 30, 2026. Free cash flow remained unavailable. A real threshold alert and detailed issuer-specific mapping review remain unverified. Contact details are kept only in the ignored local .env file.
- Paid model integration: no provider key supplied; tested using mocked HTTP responses at the external transport boundary. Model usefulness/accuracy has not been empirically evaluated on a labeled corpus.
- Docker image builds and Compose startup: A Docker runtime is not installed in this environment. CI is configured to validate Compose and the database-backed tests when the repository is pushed, but no remote CI run is claimed.

The installed Starlette version emits one deprecation warning about its httpx TestClient integration. Tests pass; this warning does not affect the application HTTP client. A future dependency update should revisit the test transport choice.

Independent review found three issues; all were reproduced and fixed with regression tests. See [decisions and review](decisions-and-review.md). No minor findings were deferred.
