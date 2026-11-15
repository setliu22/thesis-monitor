from datetime import datetime, timezone, timedelta
from sqlalchemy import select, or_, and_
from .models import Company, Job, now


def after(seconds):
    return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()


def enqueue_refresh(session, company_id: int, kind='refresh', payload=None) -> Job:
    # Serialize enqueues per company; also protects rule/refresh evaluation.
    company=session.scalar(select(Company).where(Company.id==company_id).with_for_update())
    if not company: raise ValueError('Company not found')
    existing=session.scalar(select(Job).where(Job.company_id==company_id,Job.kind==kind,Job.status.in_(['queued','running'])))
    if existing: return existing
    job=Job(company_id=company_id,kind=kind,payload=payload or {})
    session.add(job); session.flush()
    return job


def claim_job(sessions, worker_id: str, max_attempts=3, lease_seconds=180):
    with sessions.begin() as s:
        due=or_(and_(Job.status=='queued',Job.available_at<=now()),and_(Job.status=='running',Job.lease_until<now()))
        # Expired jobs at their attempt budget must not remain running forever.
        for exhausted in s.scalars(select(Job).where(due,Job.attempts>=max_attempts).with_for_update(skip_locked=True)):
            exhausted.status='failed'; exhausted.finished_at=now(); exhausted.error='Attempt limit reached after lease expiry'
        job=s.scalar(select(Job).where(due,Job.attempts<max_attempts).order_by(Job.available_at,Job.id).with_for_update(skip_locked=True).limit(1))
        if not job: return None
        job.status='running'; job.owner=worker_id; job.attempts+=1; job.lease_until=after(lease_seconds)
        s.flush(); s.expunge(job)
        return job


def owned_job(session,job_id,owner):
    job=session.scalar(select(Job).where(Job.id==job_id).with_for_update())
    if not job or job.status!='running' or job.owner!=owner or job.lease_until<now():
        raise RuntimeError('Job lease lost; discard this attempt')
    return job


def heartbeat(sessions,job_id,owner,lease_seconds=180):
    with sessions.begin() as s:
        job=owned_job(s,job_id,owner); job.lease_until=after(lease_seconds)


def finish_job(sessions,job_id,owner):
    with sessions.begin() as s:
        try: job=owned_job(s,job_id,owner)
        except RuntimeError: return False
        job.status='succeeded'; job.finished_at=now(); job.lease_until=None; job.error=None
        return True


def fail_job(sessions,job_id,owner,error,delay=30,max_attempts=3):
    with sessions.begin() as s:
        try: job=owned_job(s,job_id,owner)
        except RuntimeError: return False
        job.error=error[:1000]; job.lease_until=None
        job.status='failed' if job.attempts>=max_attempts else 'queued'
        job.available_at=after(delay)
        if job.status=='failed': job.finished_at=now()
        return True
