# Five-minute interview demo

## Prepare with genuine data

1. Start services and configure a real SEC contact identity.
2. Refresh CACI. Wait for the job to succeed. Check that reporting periods and source links match the original filing.
3. Write your actual thesis. Be ready to explain why each saved condition matters to you.
4. Choose one available metric and configure a rule that reflects your thesis. If no real threshold has been crossed, demonstrate evaluation with no alerts rather than inventing one.
5. If you need to demonstrate the alert workflow, create a clearly named **Demo threshold** chosen relative to an observed real value. Explain that this tests alert mechanics; it does not represent a changed investment view. Pause the demo rule afterwards.
6. Keep screenshots or an exported brief with capture time for an SEC outage. Describe them as previously captured data, never live data.

## Show the story

**0:00 — The problem.** “I follow US stocks, including CACI. Reading every filing manually made it hard to consistently check whether the reasons I owned a company still held.” Adapt this to your actual experience; do not claim a workflow you have not used.

**0:40 — Your thesis.** Open Thesis & rules. Explain one concrete condition, its threshold, and why quarterly versus annual matters.

**1:20 — Source evidence.** Open a metric card, inspect period start/end and tags, and open the SEC source. Show that a derived cash-flow quarter records both YTD inputs.

**2:10 — Pipeline.** Queue a refresh and switch to Activity. Explain why it returns immediately and how leases, retries and dedupe behave after a crash.

**3:00 — Alert.** Evaluate rules, inspect a real alert if available, acknowledge it, and evaluate again to demonstrate deduplication. If none triggers, show the honest no-alert result.

**3:45 — Optional narrative analysis.** If configured, analyze a filing against the saved thesis. Show a verified quote, explain limited excerpt coverage, and acknowledge that quote presence does not validate interpretation. Skip this if it has not been live-tested.

**4:30 — Tradeoffs.** Explain one decision you would change at higher scale. Open the architecture doc, then discuss tests and known limitations.

## Failure demonstration

Use an intentionally invalid SEC identity in a disposable local environment, restart services, and show the setup-needed response. The automated tests cover 429s, partial ingestion, lease recovery and replay without deliberately flooding SEC or causing paid retries.

Never put your actual email or API key on an interview screen. Keep `.env` closed. Avoid projecting private thesis details unless you choose to share them.
