# Thesis — Investment Thesis Monitor

A workspace for following US companies through SEC filings. Save your thesis and numeric rules; new eligible earnings filings are reviewed against the thesis automatically when Groq is configured.

**React + TypeScript · FastAPI · PostgreSQL · SQLAlchemy/Alembic · durable Python worker**

## Open the local app

On this Mac, double-click `Thesis Monitor.app` in the project folder. It starts
the website, API, background worker, and email process, waits for the database and
website to respond, then opens the browser. Closing the startup terminal or browser
does not stop the services. Reopening the app reuses the same supervisor and ports.
Stopped service processes are restarted automatically while the launcher is running.

Alternatively, run `npm start` from the project root, or double-click
`Start Thesis Monitor.command`. Run `npm stop` to stop services owned by the launcher.
Startup logs are private and ignored by Git under `work/local-app/`.
The macOS app entry point is a native arm64 executable. Rebuild it with
`scripts/build_macos_launcher.sh` after changing its C source or Info.plist.
A saved localhost browser bookmark alone cannot start a stopped server; use the app
launcher.

## Start locally with Docker

Install Docker Desktop (including Compose), then from this directory:

```sh
cp .env.example .env
```

Edit `.env` and set `SEC_USER_AGENT` to your name and a **real** contact email. Set `GROQ_API_KEY` to enable automatic thesis reviews; without it, financial monitoring still works. `ALPHAVANTAGE_API_KEY` enables matching earnings-call follow-up. Do not commit `.env`.

```sh
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080). Your watchlist starts empty. Add the stocks you follow, write your thesis, and save any numeric monitoring rules. The first import is a bounded baseline; later original 10-Q and 10-K filings are queued for thesis review. Suggested thresholds are examples; none are enabled automatically.

The migration container runs before the API and worker. PostgreSQL data persists in a named volume.

```sh
docker compose logs -f worker
docker compose stop
# Resume without rebuilding:
docker compose up -d
```

API reference: [http://localhost:8000/docs](http://localhost:8000/docs). Health: `/health`; database readiness: `/ready`.

## What works

- Add SEC-listed US tickers, switch the watchlist on desktop or mobile.
- Save versioned theses and rules for revenue, growth, operating margin, cash flow, capex, net income, diluted EPS, cash, assets, liabilities, equity, and supported long-term-debt balances.
- Inspect quarterly/annual history, source tags, raw input values, periods, filing accessions, and derivations.
- Queue refreshes outside HTTP requests; inspect job status, attempts, failures, and data freshness.
- Evaluate saved rules immediately; acknowledge alerts without deleting their evidence.
- Export a JSON research brief with financial provenance, thesis, rules, filings, and alerts.
- Automatically compare new original 10-Q and 10-K filings with the saved thesis; request historical or rerun reviews manually. Results show claim-level support, challenges, mixed or insufficient evidence with saved-source citations. A filing review is available before a matching call transcript arrives.

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

For local use, run PostgreSQL on your Mac and set `DATABASE_URL` in `.env` to the loopback address of that database. On macOS, install PostgreSQL with `brew install postgresql@18` and start it with `brew services start postgresql@18`. Create a database and an app login, update `.env`, and run the launcher. The launcher applies pending migrations to approved local targets and starts the API, website, monitoring worker, and email worker. Leave the Mac awake for reminders and monitoring.

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
- **Thesis review unavailable:** set `GROQ_API_KEY` and an account-supported `GROQ_MODEL`, then restart the API and worker. Save a thesis and refresh SEC data; new filings are discovered by refresh and by the scheduled submissions check. Selected filing passages, transcript passages when available, and thesis claims are sent to Groq for review. Provider quota waits are queued; model conclusions remain interpretations, not verified investment advice.
- **Stale data:** the last successful dataset stays visible after a failed refresh; errors appear in the activity feed.

This is a single-user local app. Default database credentials are local development credentials, services bind to loopback, and there is no login. Add authentication and deployment-specific secrets/network controls before hosting it publicly.

## Read next

- [Architecture and tradeoffs](docs/architecture.md)
- [Automatic claim-review implementation and verification](docs/automatic-claim-review-report.md)
- [Demo walkthrough](docs/demo.md)
- [FDE interview guide](docs/interview-guide.md)
- [Financial and operational limitations](docs/limitations.md)
- [Feature audit and remaining work](docs/feature-audit.md)
- [Verification record](docs/verification.md)
- [Implementation decisions and review](docs/decisions-and-review.md)

Primary sources: [SEC public APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [SEC access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data), [Groq structured outputs](https://console.groq.com/docs/structured-outputs).

## Always-on deployment and email

The local launcher starts the monitoring and email workers. Email requires a Resend API key and verified sender. Keep the Mac awake for scheduled monitoring. See [Local monitoring and email](docs/hosting-and-email.md).


## Shared earnings calendar

Set ALPHAVANTAGE_API_KEY in server .env or hosting secrets. The worker downloads Alpha Vantage's earnings calendar once per configured calendar interval and matches all watchlist tickers against the same response. No issuer scraper or date arithmetic is used. Provider dates are estimates, not claimed issuer confirmations. Without a key or a covered event, the next date is unavailable; initial imports and manual refresh continue to work. SEC EDGAR remains the financial statement source. Unsupported XBRL mappings remain unavailable for every issuer equally.

## Calendar, reminders, company search and charts

The app opens to the investment calendar. It combines saved-stock earnings with sourced Fed/BEA/BLS schedules and statutory federal election dates, with source status and coverage notes. Event emails default to one week and one day before at 09:00 Eastern; edit these in Calendar → Reminders. Add company searches names and tickers. Every supported metric has a historical graph and source evidence. See [calendar-search-charts.md](docs/calendar-search-charts.md) for current coverage, the blocked BLS source, reminder semantics and verification limits.
