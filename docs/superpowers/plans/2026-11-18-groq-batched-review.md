# Durable full-transcript review implementation plan

Goal: Review every transcript sentence without the 8k total cutoff, with reusable results and durable quota-aware scheduling on Groq's free tier.

Architecture: Keep the existing SQLAlchemy/Neon job queue. Persist request checkpoints and an organization-wide quota ledger in the existing generic cache table, using distinct short keys and row locks. Each worker processes bounded work, releases jobs when quota is unavailable, and resumes completed batches on its next turn. No schema change is needed. Network calls run outside database transactions.

Tasks:
1. Add tested quota admission, header-aware cooldowns, checkpoint leases, and deferred-job handling. Quota waits must not consume error retry attempts. Preserve results across worker restarts and share limits across processes.
2. Batch the complete speaker-preserving transcript catalog into bounded inputs. Review every unit, preserve original speaker/turn provenance, and deduplicate findings. Cache valid batch decisions by source text, thesis, prompt and model. Never publish a partial transcript as complete.
3. Route filing/mapping Groq calls through the same admission gate. Reuse identical finished comparisons and prevent overlapping requests with changed versions from silently returning another analysis.
4. Show queued/rate-limited progress and partial-batch counts; keep financial refresh and alerts progressing. Provide a hosted runner triggered when an analysis is requested, with periodic recovery.
5. Test rate limits, multi-company queues, checkpoint resume, full-call coverage, and real multi-stock examples. Document measured latency and quota capacity, including unavoidable free-tier limits.

Validation: SQLite unit tests, Postgres row-lock checks in CI, deterministic provider stubs for multi-stock load and restarts, bounded real Groq evaluation using existing downloaded transcripts. No investment-thesis or watchlist edits.
