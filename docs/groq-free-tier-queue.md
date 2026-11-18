# Full-call review on the Groq free tier

The app now reviews the entire available earnings-call transcript in bounded batches. It keeps short replies and negations, preserves exact source offsets and every speaker occurrence, and publishes the completed call comparison only after all distinct blocks have been classified. Repeated blocks share a relevance decision and retain their source occurrences. Filing analysis still uses thesis-ranked excerpts; full-call coverage does not imply full-filing coverage or verified investment conclusions.

## Quotas and repeat usage

Groq currently documents 8,000 tokens/minute, 200,000 tokens/day, 30 requests/minute and 1,000 requests/day for `openai/gpt-oss-20b`. Exact account limits can differ: https://console.groq.com/docs/rate-limits

The application defaults leave room below these limits: 7,800 TPM, 180,000 TPD, 25 RPM and 900 RPD. They are configurable through `GROQ_TOKENS_PER_MINUTE`, `GROQ_TOKENS_PER_DAY`, `GROQ_REQUESTS_PER_MINUTE` and `GROQ_REQUESTS_PER_DAY`. A database ledger serializes reservations across the web service, local worker and hosted scheduled worker. Full serialized prompts, source text, schema and reserved completion capacity count toward admission. Successful usage replaces estimates; provider-cached prompt tokens are excluded where reported. Provider remaining-token/reset headers and 429 Retry-After can impose additional waits, including daily limits.

No application can remove the provider's hard free-tier caps. A first full review takes minutes; several first-time reviews queue. A large portfolio imported at once may span multiple days. A typical portfolio whose companies report on different dates is a smaller ongoing workload than re-analyzing every stock every day. Reopening an unchanged completed comparison returns the saved result without Groq calls. An edited thesis needs a new review, while unchanged model batches are reusable. Historical availability still depends on the transcript provider and Alpha Vantage's separate limits.

## Recovery and fairness

Validated batch responses are content-addressed by complete request, including source text, thesis, prompt and model. SQL leases prevent overlapping workers from sending the same batch. Completed batches persist across restarts. Each job turn makes at most two new requests, then yields. Quota/provider waits return the job to the queue without consuming its error-retry budget. Genuine invalid output and configuration errors retain normal retry limits.

User activity wakes a bounded analysis worker on the hosted free web service. It claims analysis jobs only and can recover expired running leases. Polling shows phase, completed batches and next attempt. It does not wait for the hourly scheduler before starting. When Render sleeps or the browser closes, persisted jobs remain recoverable by the existing hourly GitHub runner. This is free hosting with eventual recovery, not an always-on worker guarantee.

Financial refreshes, alerts and reminders keep their existing workers. Optional mapping requests use the same budget and split large candidate lists into budgeted requests. A mapping quota wait commits structured financial data before deferring remaining mapping work, so fresh financial results are not marked stale because Groq is busy.

## Verification

- Ten-stock deterministic load: all 950 source blocks classified; exactly 30 distinct provider requests, including repeated worker reconstruction and quota deferrals. Successful batches were not repeated.
- Minute/day limits, provider 429 cooldown, invalid-output rejection, cached prompt-token accounting, changed-thesis deduplication, API result reuse, expired-job wake and short-negation preservation are covered by tests.
- PostgreSQL row-lock admission races are checked in CI; SQLite does not model row locks.
- Real Costco fiscal 2025 Q4 call: all 169 distinct source blocks classified in nine batches, including the previously missed annual warehouse-opening count. Every returned quote and speaker matched the source. The conservative live run took 438 seconds while yielding and resuming at quota boundaries. The latest defaults use a slightly smaller safety margin; latency still depends on call length and available account allowance.

The pre-existing multi-stock report is an excerpt-baseline evaluation. Its counts should not be presented as a full-call benchmark.

A call of this length used roughly 25–30k total model tokens across its batches. Six similar fresh reviews plus filing work could approach the conservative daily budget; this is an estimate, not a guaranteed stocks-per-day entitlement. Cached completed reviews use no new model requests.
