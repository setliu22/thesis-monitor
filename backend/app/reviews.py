"""One registration boundary for automatic and deliberate filing reviews.

Callers own the transaction. Company -> review -> job is the common lock order.
"""

from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import select, case
from .config import settings
from .groq_runtime import PermanentFailure
from .models import Company, Filing, ThesisVersion, Review, Job, CalendarCache, now

ANALYSIS_VERSION = "v10-direct-findings"
AUTO_FORMS = ("10-Q", "10-K")


def completion_estimate(job, state, quota, limits, at):
    """Estimate completion of the active source review from known remaining work."""
    from .groq_runtime import budget_wait

    progress = (job.payload or {}).get("progress") or {}
    phase = progress.get("phase")
    if phase not in {"filing_evidence", "filing_assessment", "call_evidence", "combined_assessment"}:
        return None
    if state.get("filing_ready") and phase.startswith("filing_"):
        return None
    try:
        remaining = int(progress["total_batches"]) - int(progress["completed_batches"])
        available = datetime.fromisoformat(job.available_at).timestamp()
    except (TypeError, ValueError, KeyError):
        return None
    if not 0 <= remaining <= 1000:
        return None
    stage = "evidence" if phase.endswith("_evidence") else "assessment"
    claims = state.get("claims") or []
    if stage == "assessment" and len(claims) == int(progress["total_batches"]):
        from .evidence import claims_with_directional_evidence

        filing_evidence = state.get("filing_evidence")
        call_evidence = state.get("call_evidence") if phase == "combined_assessment" else []
        if filing_evidence is not None and call_evidence is not None:
            directional = claims_with_directional_evidence(filing_evidence + call_evidence)
            remaining = sum(
                claim["id"] in directional for claim in claims[int(progress["completed_batches"]):]
            )
    counts = [(stage, remaining)]
    if stage == "evidence":
        if not claims:
            return None
        counts.append(("assessment", len(claims)))

    entries = list(quota.get("entries") or [])
    current = max(at, available, quota.get("blocked_until") or 0) if any(
        count for _, count in counts
    ) else at + 5
    for stage, count in counts:
        samples = [e for e in entries if e.get("stage") == stage and "seconds" in e]
        cap = min(limits.tpm, limits.tpd)
        default_cost = 6500 if stage == "assessment" else 5200
        reserved = min(
            cap, int(median(e["reserved"] for e in samples)) if samples else default_cost
        )
        used = int(median(e["tokens"] for e in samples)) if samples else reserved
        elapsed = max(5, median(e["seconds"] for e in samples)) if samples else 20
        if (
            count
            and quota.get("provider_reset", 0) > current
            and quota.get("provider_remaining", cap) < reserved
        ):
            current = quota["provider_reset"]
        for _ in range(count):
            current += budget_wait(entries, reserved, current, limits)
            entries.append({"at": current, "tokens": used})
            current += elapsed + 5
    return {
        "at": datetime.fromtimestamp(current, timezone.utc).isoformat(),
        "scope": "filing" if phase.startswith("filing_") else "filing and call",
    }


def current_thesis(s, company_id):
    return s.scalar(
        select(ThesisVersion)
        .where(ThesisVersion.company_id == company_id)
        .order_by(ThesisVersion.version.desc())
        .limit(1)
    )


def latest_filing(s, company_id):
    return s.scalar(
        select(Filing)
        .where(Filing.company_id == company_id, Filing.form.in_(AUTO_FORMS))
        .order_by(_period_column().desc(), Filing.filed.desc(), Filing.accession.desc())
        .limit(1)
    )


RECENT_EARNINGS_PERIODS = 4
RECENT_EARNINGS_ERROR = "Analysis is limited to the four most recent earnings periods."


def earnings_period(filing):
    return filing.report_date or filing.filed


def _period_column():
    return case((Filing.report_date != "", Filing.report_date), else_=Filing.filed)


def recent_earnings_periods(s, company_id):
    period = _period_column()
    return set(s.scalars(
        select(period)
        .where(Filing.company_id == company_id, Filing.form.in_(AUTO_FORMS))
        .distinct()
        .order_by(period.desc())
        .limit(RECENT_EARNINGS_PERIODS)
    ))


def recent_earnings_filings(s, company_id):
    period = _period_column()
    periods = recent_earnings_periods(s, company_id)
    filings = s.scalars(
        select(Filing)
        .where(Filing.company_id == company_id, Filing.form.in_(AUTO_FORMS), period.in_(periods))
        .order_by(period.desc(), Filing.filed.desc(), Filing.accession.desc())
    )
    winners = {}
    for filing in filings:
        winners.setdefault(earnings_period(filing), filing)
    return list(winners.values())


def require_recent_earnings(s, filing):
    if earnings_period(filing) not in recent_earnings_periods(s, filing.company_id):
        raise PermanentFailure(RECENT_EARNINGS_ERROR)


def _enqueue(s, review, allow_failed=False):
    jobs = s.scalars(
        select(Job)
        .where(
            Job.company_id == review.company_id,
            Job.kind == "analysis",
            Job.payload["review_id"].as_integer() == review.id,
        )
        .order_by(Job.id)
        .with_for_update()
    ).all()
    active = next((j for j in jobs if j.status in ("queued", "running")), None)
    if active:
        return active
    if jobs and jobs[-1].status == "failed" and not allow_failed:
        _terminal_failure(review, jobs[-1])
        return None
    job = Job(
        company_id=review.company_id,
        kind="analysis",
        payload={
            "review_id": review.id,
            "filing_id": review.filing_id,
            "thesis_id": review.thesis_id,
            "model": review.model,
            "analysis_version": review.version,
        },
    )
    s.add(job)
    s.flush()
    return job


def _terminal_failure(review, job):
    review.status = "failed"
    review.last_error = (
        job.error
        or "Review job exhausted its retry allowance; request an explicit rerun"
    )[:1000]
    review.next_attempt = None
    review.updated_at = now()


def request_review(
    s, company_id, filing_id, manual=False, rerun=False, retry_connection=False
):
    company = s.scalar(
        select(Company).where(Company.id == company_id).with_for_update()
    )
    if not company or not company.watched:
        raise ValueError("A watched company is required for review")
    filing = s.get(Filing, filing_id)
    if not filing or filing.company_id != company_id:
        raise ValueError("Filing not found for this company")
    if filing.form not in AUTO_FORMS + (("10-Q/A", "10-K/A") if manual else ()):
        raise ValueError(
            "Automatic reviews require an original 10-Q or 10-K; amendments require a manual review"
        )
    require_recent_earnings(s, filing)
    thesis = current_thesis(s, company_id)
    if not thesis or not thesis.body.strip():
        raise ValueError("Save a usable thesis before requesting a review")
    if not settings.groq_api_key.strip():
        raise ValueError("Configure Groq access before requesting a review")
    review = s.scalar(
        select(Review)
        .where(
            Review.company_id == company_id,
            Review.filing_id == filing_id,
            Review.thesis_id == thesis.id,
            Review.model == settings.groq_model,
            Review.version == ANALYSIS_VERSION,
        )
        .with_for_update()
    )
    if retry_connection:
        if not review or review.status != "provider_wait":
            return {"review": review, "job": None, "cached": False}
        job = s.scalar(
            select(Job)
            .where(
                Job.company_id == company_id,
                Job.kind == "analysis",
                Job.payload["review_id"].as_integer() == review.id,
                Job.status == "queued",
            )
            .with_for_update()
        )
        if job and (job.payload or {}).get("wait_kind") == "groq_provider":
            checked = (job.payload or {}).get("last_attempt_at")
            earliest = datetime.now(timezone.utc)
            if checked:
                earliest = max(
                    earliest, datetime.fromisoformat(checked) + timedelta(seconds=30)
                )
            new_due = min(job.available_at, earliest.isoformat())
            review.next_attempt = job.available_at = new_due
            return {"review": review, "job": job, "cached": False}
        return {"review": review, "job": None, "cached": False}
    if review is None:
        review = Review(
            company_id=company_id,
            filing_id=filing_id,
            thesis_id=thesis.id,
            model=settings.groq_model,
            version=ANALYSIS_VERSION,
            state={},
        )
        s.add(review)
        s.flush()
    elif review.status == "complete" and not rerun:
        return {"review": review, "job": None, "cached": True}
    elif review.status == "failed" and not rerun:
        return {"review": review, "job": None, "cached": False}
    if rerun and review.status in ("complete", "failed"):
        # A result can commit before its owning job acknowledges completion.
        # Preserve it while that job still owns responsibility for this review.
        active = s.scalar(
            select(Job)
            .where(
                Job.company_id == company_id,
                Job.kind == "analysis",
                Job.payload["review_id"].as_integer() == review.id,
                Job.status.in_(("queued", "running")),
            )
            .order_by(Job.id)
            .limit(1)
            .with_for_update()
        )
        if active:
            return {
                "review": review,
                "job": active,
                "cached": review.status == "complete",
            }
        # Keep immutable sources and validated responses. The pipeline resumes them.
        review.status, review.last_error, review.next_attempt = "scheduled", None, None
        review.state = {
            k: v
            for k, v in (review.state or {}).items()
            if k not in ("error", "failures", "terminal_error")
        }
    job = _enqueue(s, review, allow_failed=rerun)
    return {"review": review, "job": job, "cached": False}


def latest_status(s, company_id, filing_id=None):
    company = s.get(Company, company_id)
    if not company:
        return {"status": "unavailable", "reason": "Company not found"}
    filing, thesis = latest_filing(s, company_id), current_thesis(s, company_id)
    if filing_id is not None:
        selected = s.get(Filing, filing_id)
        if selected and selected.company_id == company_id:
            filing = selected
    result = {
        "status": "scheduled",
        "filing_id": filing.id if filing else None,
        "thesis_id": thesis.id if thesis else None,
        "thesis_version": thesis.version if thesis else None,
        "discovery_cadence_hours": 24,
        "discovery_note": "Daily submissions check while the runner is awake; hosted runs may delay discovery.",
    }
    discovery = s.scalar(
        select(CalendarCache).where(
            CalendarCache.provider == f"sec-submissions:{company_id}"
        )
    )
    if discovery and discovery.last_attempt:
        result["discovery_next_attempt"] = (
            datetime.fromisoformat(discovery.last_attempt)
            + timedelta(hours=1 if discovery.error else 24)
        ).isoformat()
    if not company.watched:
        return result | {"status": "unavailable", "reason": "Company is not watched"}
    if not thesis or not thesis.body.strip():
        return result | {
            "status": "waiting_for_thesis",
            "reason": "Save a usable thesis",
        }
    if not settings.groq_api_key.strip():
        return result | {
            "status": "configuration_required",
            "reason": "Configure Groq access",
        }
    if not filing:
        return result | {"status": "waiting_for_filing"}
    review = s.scalar(
        select(Review).where(
            Review.company_id == company_id,
            Review.filing_id == filing.id,
            Review.thesis_id == thesis.id,
            Review.model == settings.groq_model,
            Review.version == ANALYSIS_VERSION,
        )
    )
    if not review:
        prior = s.scalar(
            select(Review.id).where(Review.company_id == company_id).limit(1)
        )
        return result | {"status": "review_available" if prior else "scheduled"}
    job = next(
        (
            j
            for j in s.scalars(
                select(Job).where(
                    Job.company_id == company_id,
                    Job.kind == "analysis",
                    Job.status.in_(("queued", "running")),
                )
            )
            if (j.payload or {}).get("review_id") == review.id
        ),
        None,
    )
    # Deliberately expose only presentation metadata, never persisted source text.
    state = review.state or {}
    terminal = s.scalar(
        select(Job)
        .where(
            Job.company_id == company_id,
            Job.kind == "analysis",
            Job.payload["review_id"].as_integer() == review.id,
        )
        .order_by(Job.id.desc())
        .limit(1)
    )
    if terminal and terminal.status == "failed" and review.status != "complete":
        return result | {
            "review_id": review.id,
            "status": "failed",
            "next_attempt": None,
            "last_error": terminal.error
            or "Review worker stopped after repeated failures; retry this review.",
            "call_status": dict(state.get("call", {}), status="failed")
            if state.get("filing_ready")
            else {},
            "filing_status": "ready" if state.get("filing_ready") else "failed",
        }
    estimate = None
    if job:
        from .groq_runtime import Limits

        quota = s.scalar(select(CalendarCache.payload).where(
            CalendarCache.provider == "groq:quota:v1"
        )) or {}
        estimate = completion_estimate(
            job, state, quota,
            Limits(
                tpm=settings.groq_tokens_per_minute,
                tpd=settings.groq_tokens_per_day,
                rpm=settings.groq_requests_per_minute,
                rpd=settings.groq_requests_per_day,
            ),
            datetime.now(timezone.utc).timestamp(),
        )
    return result | {
        "review_id": review.id,
        "status": review.status,
        "next_attempt": review.next_attempt or (job.available_at if job else None),
        "last_error": review.last_error,
        "progress": (job.payload or {}).get("progress") if job else None,
        "call_status": {
            k: v
            for k, v in (state.get("call") or {}).items()
            if k in ("status", "reason", "next_attempt", "deadline")
        },
        "filing_status": "ready" if state.get("filing_ready") else "pending",
        "job_id": job.id if job else None,
        "completion_estimate": estimate,
    }


def reconcile_reviews(sessions, limit=100):
    """Bounded catch-up, plus due continuation of reviews captured under old theses."""
    count = 0
    if limit < 1:
        return count
    # A persisted cursor advances even across companies without actionable work.
    # Release it before acquiring company locks to preserve the common lock order.
    with sessions.begin() as s:
        cursor = s.scalar(
            select(CalendarCache)
            .where(CalendarCache.provider == "review-reconcile-cursor")
            .with_for_update()
        )
        if cursor is None:
            from sqlalchemy.exc import IntegrityError

            try:
                with s.begin_nested():
                    cursor = CalendarCache(
                        provider="review-reconcile-cursor", payload={}
                    )
                    s.add(cursor)
                    s.flush()
            except IntegrityError:
                cursor = s.scalar(
                    select(CalendarCache)
                    .where(CalendarCache.provider == "review-reconcile-cursor")
                    .with_for_update()
                )
        after_id = (cursor.payload or {}).get("company_id", 0)
        ids = s.scalars(
            select(Company.id)
            .where(Company.watched.is_(True))
            .order_by(case((Company.id > after_id, 0), else_=1), Company.id)
            .limit(limit)
        ).all()
        if ids:
            cursor.payload = {"company_id": ids[-1]}
    for cid in ids:
        with sessions.begin() as s:
            s.scalar(select(Company).where(Company.id == cid).with_for_update())
            previous = s.scalar(
                select(Review.id).where(Review.company_id == cid).limit(1)
            )
            filing = latest_filing(s, cid)
            checkpoint = s.scalar(
                select(CalendarCache)
                .where(CalendarCache.provider == f"discovery-baseline:{cid}")
                .with_for_update()
            )
            recovery = bool(
                checkpoint and (checkpoint.payload or {}).get("review_recovery")
            )
            if (not previous or recovery) and filing:
                try:
                    request_review(s, cid, filing.id)
                    count += 1
                    if checkpoint:
                        checkpoint.payload = dict(checkpoint.payload or {}) | {
                            "review_recovery": False
                        }
                except ValueError:
                    pass
            # Job lease exhaustion can happen outside the pipeline. Synchronize
            # responsibility into review state even when no next attempt was saved.
            latest_job_status = (
                select(Job.status)
                .where(
                    Job.company_id == cid,
                    Job.kind == "analysis",
                    Job.payload["review_id"].as_integer() == Review.id,
                )
                .order_by(Job.id.desc())
                .limit(1)
                .correlate(Review)
                .scalar_subquery()
            )
            orphaned = s.scalars(
                select(Review)
                .where(
                    Review.company_id == cid,
                    Review.status.notin_(("complete", "failed")),
                    latest_job_status == "failed",
                )
                .order_by(Review.id)
                .limit(100)
                .with_for_update()
            ).all()
            for review in orphaned:
                terminal = s.scalar(
                    select(Job)
                    .where(
                        Job.company_id == cid,
                        Job.kind == "analysis",
                        Job.payload["review_id"].as_integer() == review.id,
                    )
                    .order_by(Job.id.desc())
                    .limit(1)
                    .with_for_update()
                )
                if terminal and terminal.status == "failed":
                    _terminal_failure(review, terminal)
            if settings.groq_api_key.strip():
                pending = s.scalars(
                    select(Review)
                    .where(
                        Review.company_id == cid,
                        Review.status.notin_(("complete", "failed")),
                        Review.next_attempt.is_not(None),
                        Review.next_attempt <= now(),
                    )
                    .order_by(Review.id)
                    .limit(10)
                    .with_for_update()
                ).all()
                for review in pending:
                    call = (review.state or {}).get("call") or {}
                    deadline = call.get("deadline")
                    if (
                        (review.state or {}).get("filing_ready")
                        and call.get("status") == "pending"
                        and deadline
                        and deadline <= now()
                    ):
                        review.state = dict(review.state) | {
                            "call": dict(call)
                            | {
                                "status": "unavailable",
                                "reason": "Transcript follow-up window expired",
                                "next_attempt": None,
                            }
                        }
                        review.status, review.next_attempt = "complete", None
                        review.updated_at = now()
                        continue
                    _enqueue(s, review)
                    count += 1
    return count
