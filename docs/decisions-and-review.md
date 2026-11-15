# Implementation decisions and review

## Decisions made during execution

1. Kept implementation on `feat/thesis-monitor` in the newly created deliverable repository instead of creating a nested worktree. The repository began empty except for approved design/plan documents; no existing user code needed isolation. Cost: none to application behavior.
2. Downloaded verification tools into ignored `work/` because Node and Docker were absent. Ran PostgreSQL directly; Compose remains the primary documented delivery. Cost: container execution remains unverified without a Docker runtime, even though the official Compose configuration validator passes.
3. Fixed local Vite development at port 5174 because 5173 was occupied. The API explicitly allows that local origin. Cost: using another port requires corresponding configuration.
4. Historical quarter derivation selects prior source versions available to the current filing, rather than a later comparative revision. A regression test covers the affected case. Cost: accounting reclassifications still require manual source review; availability and matching tags cannot independently establish identical accounting policy.
5. Deferred live SEC verification until the user supplies a real SEC contact identity. No identity or financial records were invented. Cost: live CACI tag coverage and a genuine SEC-backed alert still require verification after setup.
6. Deferred paid model requests without provider credentials. The HTTP boundary, schema checks, and evidence validation were tested without a paid call. Cost: account/model compatibility and empirical output quality remain unverified.
7. Validated Compose configuration using a checksum-verified official standalone binary. No Docker runtime was available. Cost: image builds and multi-container startup still require verification in Docker.

## Independent review

A read-only review found three important issues and no critical or minor findings. All three were reproduced with failing regression tests and fixed:

- Newer reported/restated quarters now replace older derived candidates by explicit source recency, with reported facts preferred when equally current.
- The dashboard polls every 15 seconds while idle and every 3 seconds while jobs are active, and refreshes on focus/visibility. Late scheduled jobs and alerts can now appear without a manual action.
- Filing accession uniqueness and ingestion lookups are scoped by company, so different share-class tickers sharing a CIK retain their filing links. A migration preserves existing records.

After fixes, the complete local suite passed: 35 backend tests against PostgreSQL, 4 frontend workflow tests, TypeScript/Vite production build, Alembic schema consistency check, Compose configuration validation, and Python undefined/unused-name lint checks. The backend suite emits one documented upstream TestClient deprecation warning.

No minor findings were deferred. The reviewer declined live SEC, paid provider, and container-runtime checks because the required external setup was unavailable; these limits are retained in the verification record.
