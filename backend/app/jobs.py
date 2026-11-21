from datetime import datetime, timezone, timedelta
from sqlalchemy import select, or_, and_
from .models import Company, Job, Review, now


def after(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def enqueue_refresh(session, company_id: int, kind="refresh", payload=None) -> Job:
    # Serialize enqueues per company; also protects rule/refresh evaluation.
    company = session.scalar(
        select(Company).where(Company.id == company_id).with_for_update()
    )
    if not company or not company.watched:
        raise ValueError("Company not found")
    pending = session.scalars(
        select(Job).where(
            Job.company_id == company_id,
            Job.kind == kind,
            Job.status.in_(["queued", "running"]),
        )
    ).all()
    existing = next(
        (
            j
            for j in pending
            if kind != "analysis"
            or all(
                j.payload.get(k) == (payload or {}).get(k)
                for k in ("filing_id", "thesis_id")
            )
        ),
        None,
    )
    if existing:
        return existing
    job = Job(company_id=company_id, kind=kind, payload=payload or {})
    session.add(job)
    session.flush()
    return job


def claim_job(sessions, worker_id: str, max_attempts=3, lease_seconds=180, kind=None):
    with sessions.begin() as s:
        due = or_(
            and_(Job.status == "queued", Job.available_at <= now()),
            and_(Job.status == "running", Job.lease_until < now()),
        )
        if kind:
            due = and_(due, Job.kind == kind)
        # Expired jobs at their attempt budget must not remain running forever.
        for exhausted in s.scalars(
            select(Job)
            .where(due, Job.attempts >= max_attempts)
            .with_for_update(skip_locked=True)
        ):
            exhausted.status = "failed"
            exhausted.finished_at = now()
            exhausted.error = "Attempt limit reached after lease expiry"
        job = s.scalar(
            select(Job)
            .where(due, Job.attempts < max_attempts)
            .order_by(Job.available_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return None
        job.status = "running"
        job.owner = worker_id
        job.error = None
        job.payload = dict(job.payload or {}) | {"last_attempt_at": now()}
        if "waiting_for" in (job.payload or {}):
            job.payload = {k: v for k, v in job.payload.items() if k != "waiting_for"}
        job.attempts += 1
        job.lease_until = after(lease_seconds)
        s.flush()
        s.expunge(job)
        return job


def owned_job(session, job_id, owner):
    job = session.scalar(
        select(Job)
        .where(Job.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        not job
        or job.status != "running"
        or job.owner != owner
        or job.lease_until < now()
    ):
        raise RuntimeError("Job lease lost; discard this attempt")
    return job


def heartbeat(sessions, job_id, owner, lease_seconds=180):
    with sessions.begin() as s:
        job = owned_job(s, job_id, owner)
        job.lease_until = after(lease_seconds)


def finish_job(sessions, job_id, owner):
    with sessions.begin() as s:
        try:
            job = owned_job(s, job_id, owner)
        except RuntimeError:
            return False
        job.status = "succeeded"
        job.finished_at = now()
        job.lease_until = None
        job.error = None
        return True


def fail_job(sessions, job_id, owner, error, delay=30, max_attempts=3, *, retry_status="retry_wait"):
    with sessions.begin() as s:
        review = lock_job_review(s, job_id)
        try:
            job = owned_job(s, job_id, owner)
        except RuntimeError:
            return False
        job.error = error[:1000]
        job.lease_until = None
        job.status = "failed" if job.attempts >= max_attempts else "queued"
        job.available_at = after(delay)
        if job.status == "failed":
            job.finished_at = now()
        if review:
            review.status = "failed" if job.status == "failed" else retry_status
            review.last_error = error[:1000]
            review.next_attempt = None if job.status == "failed" else job.available_at
            review.updated_at = now()
            if job.status == "failed":
                state = dict(review.state or {})
                if state.get("filing_ready"):
                    state["call"] = dict(
                        state.get("call", {}),
                        status="failed",
                        reason="Call enrichment failed; the filing review remains available.",
                    )
                else:
                    state["filing_status"] = "failed"
                review.state = state
        return True


def analysis_progress(sessions, job_id, owner, phase, completed, total):
    report_progress(sessions, job_id, owner, phase, completed, total)


def report_progress(sessions, job_id, owner, phase, completed, total):
    with sessions.begin() as s:
        try:
            job = owned_job(s, job_id, owner)
        except RuntimeError:
            return False
        data = dict(job.payload or {})
        data["progress"] = {
            "phase": phase,
            "completed_batches": completed,
            "total_batches": total,
        }
        job.payload = data
        return True


def defer_job(sessions, job_id, owner, reason, delay, kind="quota"):
    with sessions.begin() as s:
        review = lock_job_review(s, job_id)
        job = owned_job(s, job_id, owner)
        payload = dict(job.payload or {})
        if kind == "groq_provider":
            failures = min(int(payload.get("provider_wait_count", 0)) + 1, 5)
            payload["provider_wait_count"] = failures
            delay = max(delay, min(900, 60 * 2 ** (failures - 1)))
        job.status = "queued"
        job.available_at = after(delay)
        job.lease_until = None
        job.owner = None
        job.error = str(reason)[:500]
        job.payload = payload | {
            "waiting_for": "groq",
            "wait_kind": kind,
        }
        if review:
            review.status = {"quota": "quota_wait", "groq_provider": "provider_wait"}.get(kind, "scheduled")
            review.next_attempt = job.available_at
            review.last_error = str(reason)[:500]
            review.updated_at = now()
        job.attempts = max(0, job.attempts - 1)


def lock_job_review(session, job_id):
    job = session.get(Job, job_id)
    if not job or not job.payload.get("review_id"):
        return None
    session.scalar(
        select(Company).where(Company.id == job.company_id).with_for_update()
    )
    return session.scalar(
        select(Review).where(Review.id == job.payload["review_id"]).with_for_update()
    )
