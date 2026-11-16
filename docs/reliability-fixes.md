# Reliability fixes

## Scheduling and execution

The worker runs scheduling in a separate thread with its own database sessions.
Slow calendar HTTP requests no longer block claiming and processing queued jobs.
Each scheduling stage catches and logs failures independently, so an earnings
provider exception does not skip reminder scheduling or SEC job creation.
Successful earnings refreshes still precede event reconciliation and reminders.
Database outages remain a shared dependency; threads do not provide process isolation.

## Missing earnings coverage

A missing earnings date previously disabled future automatic financial refreshes.
The worker now checks these stocks weekly, configurable through
`UNKNOWN_EARNINGS_REFRESH_HOURS` (default 168, minimum 24). Known earnings dates
retain the existing earnings-window schedule. Manual refresh remains available.
This is a fallback polling interval, not an estimated earnings date.

## Retry budgets

Failed first imports previously became eligible again immediately after exhausting
job retries. Automatic scheduling now respects `FINANCIAL_REFRESH_HOURS` after
the last import attempt, including companies without a successful import.
Individual jobs retain their existing bounded exponential retries.

Calendar failures now expire from the cache after one hour rather than a full
day. Previously saved payloads remain available and successful responses retain
their configured normal cache lifetime. This change applies to recorded provider
errors; unexpected exceptions still use the existing lease expiry recovery.

## Accurate completion reporting

A worker that loses its job lease no longer logs successful completion when
`finish_job` rejects its ownership. Existing ownership checks still protect writes.

## Checks

No automated tests were added or run for this change. Static lint and compilation
checks are recorded in the accompanying chat. These changes do not deploy the
app to an always-on host or establish inbox delivery confirmation.
