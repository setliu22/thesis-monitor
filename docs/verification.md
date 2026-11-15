# Verification record

Verified locally on November 14, 2026 (America/New_York). This record distinguishes deterministic checks from external integrations that still need user configuration.

## Executed

- Python backend suite against a separate PostgreSQL 16.4 database: storage, financial normalization, SEC transport behavior, durable jobs, replay, lease recovery, actual SKIP LOCKED behavior, rule evaluation, API validation, local-origin protection, optional analysis boundary, and migration upgrade tests.
- Frontend workflow tests: empty-data/setup state, thesis save, and failed rule-save draft preservation.
- TypeScript check and Vite production build.
- PostgreSQL server restart followed by an actual API read: saved demo thesis and paused rule remained persisted.
- Alembic initial migration and subsequent schema upgrade on a genuine PostgreSQL database.
- Browser preview against the actual API/database: mobile layout, thesis save, and paused-rule save. The preview's thesis/rule are clearly marked demo records used to exercise editing; no financial data or alerts were invented.
- Compose YAML parsing and resolution of the shared environment anchor. This is a syntax/structure check, not `docker compose config` or a container startup.

## External checks pending

- Live SEC calls, actual CACI tag review, and a real financial alert: pending a valid user-supplied SEC contact identity. The application deliberately starts in a visible setup-needed state instead of inventing contact information or financial records.
- Paid model integration: no provider key supplied; tested using mocked HTTP responses at the external transport boundary. Model usefulness/accuracy has not been empirically evaluated on a labeled corpus.
- Docker image builds and Compose startup: Docker CLI/runtime is not installed in this environment. CI is configured to validate Compose and the database-backed tests when the repository is pushed, but no remote CI run is claimed.

The installed Starlette version emits one deprecation warning about its httpx TestClient integration. Tests pass; this warning does not affect the application HTTP client. A future dependency update should revisit the test transport choice.
