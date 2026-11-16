# Investment calendar, search and metric histories

## Using the app

Calendar is the landing page. Choose a month using arrows or the month picker. Earnings for stocks marked Invested appear alongside scheduled macro events; Following-only stocks are excluded by default and can be included using Investments only. Mark investment status on Overview. Existing watchlist entries initially count as investments; this is not broker account synchronization.

Select a date for event details, published/estimated status, Eastern release time when supplied, and the source link. Mobile dates use colored dots; tapping a date moves to its details. Category filters control the view independently from email preferences. Missing earnings are listed, not fabricated.

Reminders opens editable email settings. The user's selected defaults are seven and one days before, at 09:00 America/New_York. Email is enabled using the existing Resend credentials/recipient. Preferences can disable reminders or categories and change the hour. A server must be running on the reminder day. Missed previous days are not backfilled. Date-only events have no invented release time. This is a schedule, not a claim that each event will move a stock in a particular direction.

Company search in Add company matches ticker and company name after a 250ms debounce. Choose a result with the keyboard or mouse/touch. SEC's company exchange directory is cached server-side, so typing does not make a new SEC request per letter. Selecting a result uses the existing add/import flow.

Overview shows a history graph under all 15 supported metrics. Click a card for full history and source evidence. Quarterly, annual and instant balances remain separate. Balance-sheet metrics are available in the larger chart selector too. Financial-history table metric labels have mini charts, and selected values show a full history. Missing values are not plotted as zero; fewer than two comparable observations produces an explicit empty state.

## Sources and current coverage

- Earnings: existing Alpha Vantage shared bulk calendar, filtered by saved investment tickers. Provider dates are estimated and may change. The provider currently has no CACI event; that stock remains explicitly missing.
- Fed: Federal Reserve published FOMC meeting calendar. Events say meeting concludes, not a promised rate decision or outcome. Covers years currently published on the source page.
- BEA: official iCalendar feed, narrowed to national GDP and Personal Income and Outlays (including PCE). Local county/state releases are excluded.
- BLS: official iCalendar feed, filtered to CPI/PPI and employment/JOLTS releases. This machine receives HTTP 403. The app reports the source unavailable, does not bypass the block, and cannot display those dates without a successful source response.
- Federal elections: general Election Day's statutory recurring schedule, with a legal source link. No individual date is baked into the code. Statutory federal elections are distinguished from issuer/provider forecasts. The 2026 midterms are correctly shown as past on November 3; future federal election dates can be viewed using the month picker.

This does not claim coverage of every global political event, budget deadline, company product launch, emergency announcement or unscheduled market shock. Feed errors and last-check dates are under Sources & coverage. Cached dates may be stale during a source outage.

## Persistence and reminder behavior

MarketEvent stores source identity, day, optional UTC timestamp, category, status, revision and investment relationship. The feed cache uses database leases and bounded HTTP reads, with network calls outside database transactions. Successful source refresh reconciles future events; failed refresh retains previous records. No source error can silently masquerade as a fresh complete schedule.

The existing durable Delivery outbox now supports numeric alerts or scheduled events. Reminder identity includes event, revision, lead time and recipient. The worker refreshes earnings, reconciles events, then queues due reminders once per minute. The email dispatcher rechecks the event revision, active state, investment flag, current settings, expiry and delivery hour before sending. Pending reminders that become invalid are cancelled. Safely cancelled reminders can be re-enabled within their original window, keeping the same payload/provider key. Provider acceptance is not inbox confirmation, and an already in-flight/accepted email cannot be recalled after a last-second schedule change.

One owner settings row serializes reminder creation. Provider retry backoff and the 23-hour idempotency safety window remain in force. Reminders expire at local midnight of their selected reminder day; outdated reminders do not accumulate after a long server outage.

## Checks for this update

Applied the event/outbox migration to development PostgreSQL. Checked live calendar results (national GDP, personal-income/PCE release, Fed meeting and federal election), live name search (Microsoft resolves to MSFT), saved reminder preferences, the browser calendar/day detail, expanded historical charts and the company search dropdown. Production TypeScript/Vite build, Ruff F checks, Compose configuration and Render schema validation passed. Independent read-only review found reminder ordering, re-enable and changed-hour defects; all were fixed and reviewed. Existing frontend fixtures were updated for the Calendar landing page and blank rule defaults. No automated test suite was run for this update. No synthetic email was sent.
