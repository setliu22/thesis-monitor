# Calendar, search and metric histories implementation plan

> Implement inline with the executing-plans workflow. User requested these features and selected reminders seven days and one day before. Do not add or run tests without a user request.

**Goal:** One clean calendar for saved investments and scheduled market events, searchable company selection, and history under every metric.

**Architecture:** Preserve React/FastAPI/PostgreSQL. Source earnings from existing Alpha Vantage cache, macro events from official published schedules (BLS and Fed), federal elections from official FEC schedule data. Persist normalized events and feed status; never fabricate an earnings date or impact prediction. Extend the durable email outbox for scheduled reminders, storing unique event/revision/lead-time identities. Date changes cancel pending reminders. Search SEC company names/tickers from a shared durable cache; debounce UI requests and support keyboard selection. Use a reusable chart component for all numeric metrics and table inspection, keeping quarter, annual and instant data separate.

**Decisions:** Existing watchlist is the starting investment list; add an Invested/Following switch and filter calendar earnings to invested stocks by default. Calendar month grid on desktop, compact dots and agenda on mobile, selected-day details, category filters and source links. Missing earnings are listed explicitly. Reminders default to [7,1] days before at 09:00 America/New_York for date-only events; settings are editable. Notify for sourced scheduled events, not news predictions.

## Steps
- [x] Add persisted calendar events, feed status, holdings flag and reminder preferences; extend email deliveries for events.
- [x] Add bounded official feed adapters, reconciliation, cached company search and calendar API.
- [x] Add durable reminder creation/cancellation and integrate workers.
- [x] Add search suggestions, calendar screen, holdings/reminder controls and metric charts.
- [x] Apply migrations; check build/configuration/live data/UI; independent review; document limits and complete.
