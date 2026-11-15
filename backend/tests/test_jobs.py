from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.models import Job
from app.jobs import enqueue_refresh, claim_job, finish_job, fail_job


def test_enqueue_deduplication_and_retry_limit(sessions):
    with sessions() as s:
        first=enqueue_refresh(s,1); s.commit()
    with sessions() as s:
        assert enqueue_refresh(s,1).id==first.id; s.commit()
    for n in range(3):
        job=claim_job(sessions,'worker',max_attempts=3)
        assert job.attempts==n+1
        fail_job(sessions,job.id,'worker','network',delay=0,max_attempts=3)
    assert claim_job(sessions,'worker') is None
    with sessions() as s: assert s.get(Job,first.id).status=='failed'


def test_expired_lease_is_reclaimed_and_old_owner_cannot_finish(sessions):
    with sessions() as s: enqueue_refresh(s,1); s.commit()
    first=claim_job(sessions,'dead')
    with sessions() as s:
        s.get(Job,first.id).lease_until=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(); s.commit()
    recovered=claim_job(sessions,'alive')
    assert recovered.id==first.id and recovered.attempts==2
    assert not finish_job(sessions,first.id,'dead')
    assert finish_job(sessions,first.id,'alive')


def test_competing_claims_do_not_return_same_job(sessions):
    with sessions() as s: enqueue_refresh(s,1); s.commit()
    assert claim_job(sessions,'one') is not None
    assert claim_job(sessions,'two') is None


def test_skip_locked_lets_another_worker_claim_other_company(sessions):
    import pytest
    from app.models import Company
    if sessions.kw['bind'].dialect.name!='postgresql': pytest.skip('Requires PostgreSQL row locks')
    with sessions() as s:
        s.add(Company(ticker='TEST',name='Synthetic Test Company',cik='0000000001')); s.flush()
        first=enqueue_refresh(s,1); second=enqueue_refresh(s,2); s.commit()
    with sessions() as blocker:
        blocker.scalar(select(Job).where(Job.id==first.id).with_for_update())
        claimed=claim_job(sessions,'competitor')
        assert claimed.id==second.id
