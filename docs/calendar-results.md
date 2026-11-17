# Calendar results

Past calendar cells show the reported value and its direction. Selecting a day shows the previous value, change, reference periods and watchlist context without leaving the app.

## Sources and comparisons

- ALFRED release-date vintages supply CPI, PPI, PCE, payrolls, unemployment, job openings, real GDP growth and the Federal Reserve target-rate range.
- Monthly inflation compares monthly percentage changes, not index levels. Slower positive inflation means prices still rose.
- Payroll changes measure jobs added; job openings are a separate level. GDP is annualized real quarterly growth.
- Fed decisions use next-day effective target rates compared with the meeting day and wait for next-day data.
- Earnings compare matching fiscal-period SEC results with compatible prior-year facts. They do not measure surprises against analyst consensus.
- Election outcomes have no connected verified results feed and remain explicitly unavailable.

The parser rejects unversioned data and vintages later than requested. ALFRED may return an earlier effective vintage when no newer observation exists. Requested vintages are saved in source metadata. Prior-period figures can include revisions already known on the release date; later revisions are excluded.

## Persistence and scheduling

A JSON outcome is stored on each market event. The existing scheduled worker processes a bounded batch of past events from the last 400 days. Pending results retry after an hour; recent vintages have an hourly cache, historical vintages a long cache. Final results persist across browser sessions. Event identity or date changes invalidate the outcome. Concurrent late failures cannot overwrite a saved final result.

Company context is derived from watchlist holdings and financial source facts filed by the event date. Current saved thesis references are explicitly labeled current. Debt, cash and cash flow provide exposure clues; fixed versus floating debt, maturity dates and business sensitivity still require research. These explanations are not stock recommendations or automated buy/sell signals.
