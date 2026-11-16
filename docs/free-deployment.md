# Free deployment

## Components

- Render Free web service: serves the UI and API, sleeps when idle.
- Neon Free PostgreSQL: stores watchlists, rules, filings, jobs and email receipts.
- GitHub Actions: `.github/workflows/monitor.yml` runs hourly at minute 17 UTC
  and supports manual runs. It schedules work, processes up to 20 jobs, sends
  bounded batches of due messages and receipt checks, then exits.
- Resend: existing email provider. A Full Access key is required for both send
  and receipt lookups; sending-only keys cannot confirm delivery.

The browser and sleeping web service do not control background runs. This is
best-effort hosted scheduling, not a continuously running worker or guaranteed
09:00 reminder service. GitHub may delay or drop scheduled runs. Delayed runs
can send reminders later on the same Eastern calendar day; existing rules do
not backfill expired reminder days. Public repository schedules can be disabled
after inactivity. Keep the source repository private and watch Actions failures.

## Activation

1. Create a Neon Free project. Use its TLS PostgreSQL connection string for
   `DATABASE_URL`. Keep the password private. Use the same database in Render
   and GitHub. Do not use Render's expiring free database.
2. Connect the private source repository to Render. Select Blueprint file
   `render.free.yaml`. This creates only a Free web service. Do not select
   `render.yaml`, which provisions paid resources.
3. Set Render's prompted secrets. `APP_ORIGIN` must be the exact HTTPS service
   URL, without a trailing slash. Retrieve its generated owner password privately.
   Login username is `owner`. Leave the optional OpenAI key blank if unused.
   Startup applies Alembic migrations before accepting web traffic.
4. Add GitHub Actions repository secrets: `DATABASE_URL`, `DATABASE_URL_UNPOOLED`, `SEC_USER_AGENT`,
   `ALPHAVANTAGE_API_KEY`, `RESEND_API_KEY`, `EMAIL_FROM`, `ALERT_EMAIL`,
   `APP_ORIGIN`, and optionally `OPENAI_API_KEY`. These values must match the
   web service. Never put them in repository files or workflow source.
5. Run the Investment monitor workflow manually once. Inspect its conclusion,
   hosted `/ready`, saved companies, rules and calendar before relying on it.
6. Preserve local data by transferring a PostgreSQL custom-format backup into
   the new empty database before starting workers. Keep the original database.
   Do not restore onto an active/nonempty database. Backups contain private
   thesis and recipient data and must remain outside the repository.

## Usage limits

Free plans have limits, not an unlimited uptime guarantee. Neon currently lists
100 CU-hours/month and 1 GB storage/project. Hourly short runs let it suspend
between work; continuous browser polling can increase compute use. GitHub
private repositories consume the account's included Actions minutes. Keep
Actions overage spending disabled. Monitor both providers' usage dashboards.

Reference documentation:
- https://render.com/docs/free
- https://neon.com/pricing
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

## Delivery receipts

The notifier and scheduled runner retrieve the latest event from Resend once
per hour for up to seven days after the first sending attempt. A database claim
prevents simultaneous lookup of the same row. GET requests never resend mail.
The original send status remains separate from `receipt_event`, so receipt
failures cannot return a sent message to the send queue. Bounces, complaints,
failures, suppression and cancellation stop further lookups and appear in Alerts.
Delivered/opened/clicked messages continue bounded checks to capture later
complaints. Read permission errors are visible without exposing provider bodies.
If no final delivery event arrives within seven days, the UI preserves the last known event and shows an unconfirmed-delivery warning.
`delivered` means acceptance by the receiving mail server, not inbox placement.

Reference: https://resend.com/docs/api-reference/emails/retrieve-email

## Current activation state

Deployment files and receipt code are implemented. Account provisioning,
secret installation and the live workflow must be completed before claiming
the system operates with the laptop off. A manifest alone is not deployment.
