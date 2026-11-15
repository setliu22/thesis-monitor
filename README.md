# Thesis — Investment Thesis Monitor

A CACI-first workspace for following US companies through SEC filings. Write a thesis, choose the financial changes worth watching, and inspect the filing evidence when a rule triggers.

**React + TypeScript · FastAPI · PostgreSQL · SQLAlchemy/Alembic · durable Python worker**

## Start locally with Docker

Install Docker Desktop (including Compose), then from this directory:

```sh
cp .env.example .env
```

Edit `.env` and set `SEC_USER_AGENT` to your name and a **real** contact email. Leave `OPENAI_API_KEY` empty unless you want optional model analysis. Do not commit `.env`.

```sh
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080). CACI is added on first opening. Click **Refresh SEC data**, then write your own thesis and save monitoring rules. Suggested thresholds are examples; none are enabled automatically.

The migration container runs before API and worker startup. PostgreSQL data persists in a named volume. Keep the worker running for scheduled refreshes. Alerts appear inside the app; there is no email delivery in this version.

```sh
docker compose logs -f worker
docker compose stop
# Resume without rebuilding:
docker compose up -d
```

API reference: [http://localhost:8000/docs](http://localhost:8000/docs). Health: `/health`; database readiness: `/ready`.

## What works

- Add SEC-listed US tickers, starting with CACI; switch the watchlist on desktop or mobile.
- Save versioned theses and rules for revenue, growth, operating margin, cash flow, capex, and supported long-term-debt balances.
- Inspect quarterly/annual history, source tags, raw input values, periods, filing accessions, and derivations.
- Queue refreshes outside HTTP requests; inspect job status, attempts, failures, and data freshness.
- Evaluate saved rules immediately; acknowledge alerts without deleting their evidence.
- Export a JSON research brief with financial provenance, thesis, rules, filings, and alerts.
- Optionally analyze bounded filing excerpts against a saved thesis using the OpenAI Responses API. Only observations whose quotes occur in supplied text are shown. Interpretation remains model-generated.

## Local development

Requires Python 3.12+, Node 22+, and PostgreSQL 16+. Docker can supply just PostgreSQL:

```sh
docker compose up -d db
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock.txt
# .env uses localhost PostgreSQL by default.
.venv/bin/alembic -c backend/alembic.ini upgrade head
.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In another terminal, from the project directory:

```sh
PYTHONPATH=backend .venv/bin/python -m app.worker
```

In a third terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open [http://localhost:5174](http://localhost:5174). The port is fixed so local origin checks remain predictable; if occupied, stop the conflicting development server or configure both Vite and the API allowlist together. API and worker load `.env` from the project working directory. Restart both after changing environment settings.

The `work/` directory, if present in this generated workspace, contains ignored local verification tools and logs. It is not part of the project or required to run it. Use the documented dependencies above for a new checkout.

## Tests

Never point `TEST_DATABASE_URL` at a database you want to keep: the test fixture creates and drops the application's tables. Use a separate database named `thesis_test`.

```sh
# Create an isolated test database in the Compose database container:
docker compose exec db createdb -U thesis thesis_test
TEST_DATABASE_URL=postgresql+psycopg://thesis:thesis@localhost:5432/thesis_test \
  .venv/bin/python -m pytest -c backend/pytest.ini backend/tests -q
cd frontend
npm test
npm run build
```

Without `TEST_DATABASE_URL`, backend tests use temporary SQLite databases; the PostgreSQL row-lock test skips. PostgreSQL is required to verify locking semantics. Tests use explicitly synthetic financial inputs and mocked SEC/provider transport boundaries. They do not contact SEC, make paid model calls, or send messages.

## Data setup and troubleshooting

- **SEC identity required:** fill `SEC_USER_AGENT` in `.env` with your real name/contact address; restart API and worker. Placeholder example domains are rejected.
- **HTTP 403 from SEC:** access may be blocked by SEC network policy even with a valid identity. Keep the error visible and retry later; do not disable TLS or attempt to bypass restrictions.
- **Refresh stays queued:** check the worker logs and database connectivity. Jobs are durable; no refresh runs inside the API handler.
- **New filing, missing metrics:** submissions may appear before XBRL facts. The app shows pending status and retries on later refreshes.
- **Unavailable metric:** source facts may be absent or lack a compatible comparison period. Click its card for the reason; missing data cannot trigger a numeric rule.
- **No alert:** save an enabled rule, select the intended period, then evaluate. A threshold must actually be met. Existing alerts are deduplicated per rule version and observation.
- **Optional analysis unavailable:** set `OPENAI_API_KEY` and an account-supported `LLM_MODEL`, restart services, save a thesis, then choose Analyze on a 10-K or 10-Q. Requests can incur provider charges. Selected excerpts and your thesis are sent only when an analysis job is requested.
- **Stale data:** the last successful dataset stays visible after a failed refresh; errors appear in the activity feed.

This is a single-user local app. Default database credentials are local development credentials, services bind to loopback, and there is no login. Add authentication and deployment-specific secrets/network controls before hosting it publicly.

## Read next

- [Architecture and tradeoffs](docs/architecture.md)
- [Demo walkthrough](docs/demo.md)
- [FDE interview guide](docs/interview-guide.md)
- [Financial and operational limitations](docs/limitations.md)
- [Verification record](docs/verification.md)

Primary sources: [SEC public APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [SEC access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data), [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
