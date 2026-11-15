# FDE interview guide

## A concise project explanation

“I built an investment thesis monitor around stocks I follow, starting with CACI. It turns my thesis into explicit financial conditions, ingests real SEC filings, and shows which condition changed with the underlying source evidence. The core is a React/FastAPI/PostgreSQL app with a durable worker. The hard part was matching financial periods and making retries safe. Optional LLM analysis handles narrative excerpts, with exact supporting quotes checked before display.”

Use this only after running the project and understanding the decisions. Say which parts were AI-assisted, what you reviewed, and which behavior you verified personally.

## Why this demonstrates FDE work

| Interview area | Concrete project evidence | Be prepared to explain |
|---|---|---|
| Problem discovery | Personal CACI watchlist and editable thesis | What you were doing before; what makes an alert useful |
| Integration | SEC submissions, companyfacts, ticker mapping | Identity requirements, network blocks, data arriving at different times |
| Data modeling | Versioned theses/rules, source snapshots, observations | Why alert evidence must survive a later thesis edit or restatement |
| SQL | Uniqueness, foreign keys, row locks, leases | Why SKIP LOCKED helps a queue and why enqueue needs a company lock |
| Pipelines | Separate discovery/normalization stages | How partial failure preserves filing records and last good metrics |
| Applied LLMs | Structured narrative observations and quote validation | What validation proves, what it cannot prove, and how to evaluate usefulness |
| Product delivery | Complete UI, setup, migrations, tests, docs | How someone else runs it and recognizes stale/unavailable data |

## Questions you should be able to answer

**Why not compare the latest two filings?** A filing may include year-to-date values, comparative periods, or amendments. A nine-month cash-flow figure is not a single quarter. Select compatible durations first, derive quarters explicitly, and compare equivalent prior-year periods.

**What happens if the worker dies?** Its lease expires. Another worker can reclaim the job. Writes require current ownership. Upserts and uniqueness prevent repeated filings/alerts. External model calls can repeat, so exactly-once execution is not claimed.

**Why PostgreSQL for the queue?** The project has modest personal throughput and already needs a relational database. Durable job state and row locks avoid another service. At higher concurrency, measure database contention before moving scheduling/execution to a dedicated queue.

**Why store raw snapshots?** They make normalization and alert investigations reproducible. Content hashes dedupe repeated responses. Retention policies would be needed for long-term or multi-user operation.

**Why not ask the LLM to calculate everything?** Thresholds need reproducible arithmetic and exact periods. The model is more useful for narrative disclosures. Grounding checks reduce unsupported output but do not establish investment truth.

**How would you test the model?** Build a small labeled set of actual excerpts with expected support/challenge/unclear judgments. Measure valid-quote rate, unsupported-observation rate, missed material changes, agreement with manual labels, latency and cost. The repository currently tests schema/quote boundaries; it does not claim an empirical quality score.

**How would you make this multi-user?** Add authentication, ownership to every query, tenant-aware uniqueness, private thesis isolation, shared public filing ingestion, per-user evaluations and notification preferences. Reassess rate budgets and provider data handling before deployment.

**What would you improve next?** First use it for several filing cycles. Record missed alerts, noisy rules and manual corrections. Let those observations decide whether to improve metric coverage, add carefully scoped backlog extraction, or add outbound notifications.

## Claims to avoid

Do not invent production users, time savings, alpha, prediction accuracy, uptime, ingestion throughput, or LLM accuracy. Do not say a quote check eliminates hallucinations. Do not describe pending SEC verification as completed. Do not imply that a generated threshold is your investment thesis.

## Build evidence through use

Keep a log with filing accession, source period, review timestamp, rule, alert usefulness, corrections, and minutes spent reviewing. After several genuine observations, report the measured result with its sample size. A small honest result is more useful than a fictional enterprise impact claim.
