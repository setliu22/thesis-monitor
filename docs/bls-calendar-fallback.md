# BLS calendar fallback

On 2026-11-16, direct requests to the official BLS ICS calendar and schedule HTML
returned HTTP 403 with the AkamaiGHost server header. This identifies the serving
edge, not the precise blocking rule. No authentication bypass, proxy rotation or
browser impersonation is used.

The BLS adapter now falls back to the St. Louis Fed's public FRED release calendar.
It uses the calendar's GET form fields (`rid`, `vs`, `ve`) to request published
dates for CPI, PPI, Employment Situation and JOLTS. No API key is required by this
public HTML calendar. Dates are read from the response, never extrapolated.

The bounded window is 35 days before today through 180 days ahead. This does
not imply that all dates in that horizon have been announced. FRED timestamps
are US Central Time and are converted to UTC; the app displays Eastern Time.
The source label reads “BLS via FRED” and events link to the source calendar.

All four release pages must contain readable events before replacing the shared
cache. A failure or unreadable page retains the prior complete payload. Identical
release/date keys are used for direct BLS and FRED results so changing sources
does not create a second event. The existing daily cache and hourly error retry
still apply.

Live source loading retrieved ten release dates, including December 1 JOLTS,
December 4 Employment Situation, December 10 CPI and December 15 PPI, all 2026.
No automated tests were added or run; frontend production build and Python
basic lint passed. A read-only review identified partial-response cache withdrawal,
which is addressed by requiring readable events from every requested release.

Separately, the companies' own pages were checked on 2026-11-16: Microsoft says
its next earnings date will be announced soon, and CACI lists no upcoming events.
Missing earnings calendar entries alone do not establish a provider defect.

Sources:
- https://fred.stlouisfed.org/releases/calendar
- https://www.bls.gov/help/hlpiCAL.htm
- https://www.microsoft.com/en-us/investor/default
- https://investor.caci.com/events
