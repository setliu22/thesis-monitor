# Hosting and email alerts

## Implemented

The API, SEC sync worker and email dispatcher run independently of the browser. PostgreSQL stores watchlists, rules, filings, jobs, alerts and delivery attempts. A root Dockerfile builds the React UI and serves it through FastAPI on the same origin. `render.yaml` defines three paid services and managed PostgreSQL; the database denies public connections. No cloud resources have been created yet.

When a rule matches, the alert and email outbox row commit in the same transaction. A dispatcher claims due rows with `FOR UPDATE SKIP LOCKED`, commits its lease, then calls Resend outside the transaction. A crashed process leaves a recoverable two-minute lease. Retries reuse an immutable payload and UUID idempotency key, use exponential delay with jitter, and stop after six attempts. Permanent rejection is retained as failed. After 23 hours from the first attempt, requests become uncertain and require provider reconciliation before any resend. Resend retains idempotency keys for 24 hours: https://resend.com/docs/dashboard/emails/idempotency-keys

Accepted means Resend acknowledged the request. It does not confirm inbox delivery. Bounce/webhook tracking is not implemented. Failed/uncertain deliveries are visible in Alerts; there is deliberately no blind resend button that could duplicate an uncertain email. Old in-app alerts are not backfilled into email. Email is queued only when sender, recipient and API key are configured. New matching observations or rule versions may each generate an alert; this is a condition monitor, not a breach/recovery state machine.

## Activation

1. Connect the suggested Render plugin/account. The Blueprint requires a Git repository containing this source. No remote repository is configured yet.
2. Review the paid resource estimate before provisioning: three `0.5c-512mb` services and one `0.1c-256mb` PostgreSQL instance with 5 GB storage. Use the current Render checkout quote; no billing has been accepted.
3. Create the Blueprint from `render.yaml`. Supply the web service's prompted secrets: SEC_USER_AGENT, APP_ORIGIN (its exact HTTPS public URL), RESEND_API_KEY, EMAIL_FROM (a Resend verified sender), ALERT_EMAIL. The confirmed recipient is stored only in ignored local .env; set the same recipient in Render. The workers reference these values from the web service on Blueprint sync. After secret changes, sync/redeploy all three services so references stay current.
4. Render generates OWNER_PASSWORD. Retrieve it privately from service settings. Browser sign-in uses username `owner`. Production refuses requests until HTTPS origin and a password of at least 24 characters are configured. Basic authentication protects the frontend and API; use the Render HTTPS URL. This is a single-owner app, without multi-user accounts or account recovery.
5. The web service runs Alembic before deploying. Workers may initially retry while migrations finish. Check `/ready`, the worker logs and `/api/notifications`. Readiness checks database connectivity, not worker liveness; there is no external uptime monitor yet.
6. Copy the existing database using PostgreSQL backup/restore if preserving local watchlists and historical data is desired. Keep the local database intact until hosted counts and saved rules match. Backups/restore must be checked before relying on the service; no cloud restore has been exercised here.
7. Save a real rule, then verify a matching alert reaches the confirmed inbox. No live email has been sent during implementation; provider behavior was tested with an HTTP mock.

The app will continue operating with the laptop off only after these hosted services are actually deployed and email credentials are supplied. A deployment manifest alone does not supply that uptime.

## Local run

Add ALERT_EMAIL, EMAIL_FROM and RESEND_API_KEY to ignored `.env`, then restart the API and workers. Start `PYTHONPATH=backend .venv/bin/python -m app.notifications` alongside the existing SEC worker. Docker Compose includes the notifier and restart policies; it still stops when the computer stops. Configuration and health checks do not send test mail.

## Interview explanation

“I separated ingestion, evaluation and notification delivery. The browser reads precomputed PostgreSQL results. Rule evaluation writes the alert and an outbox message atomically, so a committed alert cannot lose its email task between a database commit and a network call. Dispatch is at least once; a stable provider idempotency key limits duplicate side effects. Leases recover crashed workers, and bounded retry prevents a broken provider from causing an endless loop. When the deduplication window expires, I expose uncertainty instead of claiming exactly-once delivery.”

Hosting reference: https://render.com/docs/blueprint-spec

## Earnings scheduling update

Activity and sync history have been removed from navigation. Alerts remain on Overview; operational job records remain in PostgreSQL for troubleshooting. The hourly financial refresh is replaced by daily checks within an earnings window. A company without data still gets its initial import; manual refresh remains available.

For CACI, the worker checks the issuer's latest 100 news releases once a day and reads up to two conference-call scheduling announcements. A parsed issuer release date is labeled confirmed. Until one is available, the prior SEC 10-Q/10-K filing date plus 91 days is explicitly labeled an estimate. Other tickers currently use this estimate; automatic issuer calendar discovery is CACI-specific. Calendar errors retain the prior schedule and an error in the API.

Confirmed dates start refreshes at 4:30 p.m. America/New_York on release day; estimated dates use a window from 14 days before through 30 days after the estimate. SEC data is checked at most daily during the window. Refreshes stop once the new 10-Q/10-K and its revenue observation are both present, so an early submissions entry does not suppress companyfacts follow-up. Dates are recalculated after a new loaded report. If reports remain unavailable after the window, manual refresh is needed; this is not comprehensive monitoring of off-cycle 8-Ks, restatements or every late filing. REFRESH_SECONDS no longer controls automatic financial refresh scheduling.

For a first email test, sign up for Resend using the alert recipient's address, set EMAIL_FROM=onboarding@resend.dev, and add a sending API key. This default domain only supports test email to the Resend account's own address. Regular sending needs an owned, verified domain. See https://resend.com/docs/knowledge-base/403-error-resend-dev-domain . Never paste the API key into chat; store it in the ignored .env or hosting secrets. API and notifier must be restarted after environment changes. No email was sent during this update.
