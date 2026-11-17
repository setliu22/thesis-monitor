"""Run exactly one worker service: python -m app.worker.

Database leases permit recovery. One deployment worker owns the SEC rate gate.
"""

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from .config import settings
from .db import SessionLocal, sec_gate
from .models import Company
from .earnings import update_calendar, refresh_due, latest_loaded_report
from .sec import SecClient, valid_identity
from .jobs import enqueue_refresh, claim_job, heartbeat, finish_job, fail_job
from .ingest import ingest_company

logger = logging.getLogger("thesis.worker")


def schedule(sessions=SessionLocal):
    from .events import refresh_events, queue_reminders

    # Keep independent services progressing when one provider fails.
    for task in (update_calendar, refresh_events, queue_reminders):
        try:
            task(sessions)
        except Exception:
            logger.exception("schedule_task_failed: %s", task.__name__)
    if not valid_identity(settings.sec_user_agent):
        return
    with sessions.begin() as s:
        for company in s.scalars(select(Company).where(Company.watched.is_(True))):
            filing = latest_loaded_report(s, company.id)
            if refresh_due(company, datetime.now(timezone.utc), filing):
                enqueue_refresh(s, company.id)


def process_once(sessions=SessionLocal, client=None, owner=None):
    owner = owner or uuid.uuid4().hex
    job = claim_job(sessions, owner, settings.max_attempts, settings.lease_seconds)
    if not job:
        return False
    stop = threading.Event()

    def renew():
        while not stop.wait(settings.lease_seconds / 3):
            try:
                heartbeat(sessions, job.id, owner, settings.lease_seconds)
            except Exception:
                logger.exception("heartbeat_failed")
                return

    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        if job.kind == "refresh":
            ingest_company(
                sessions,
                job.company_id,
                client or SecClient(settings.sec_user_agent, gate=sec_gate),
                job.id,
                owner,
            )
        elif job.kind == "analysis":
            from .analysis import run_analysis_job

            run_analysis_job(sessions, job, owner)
        else:
            raise ValueError("Unknown job kind")
        if not finish_job(sessions, job.id, owner):
            logger.warning("job_completion_discarded: lease lost for job %s", job.id)
            return True
        logger.info(
            json.dumps(
                {
                    "event": "job_succeeded",
                    "job_id": job.id,
                    "company_id": job.company_id,
                }
            )
        )
    except Exception as exc:
        error = (
            "Database operation failed; no result saved. Retry after the app updates."
            if isinstance(exc, SQLAlchemyError)
            else str(exc)
        )
        fail_job(
            sessions,
            job.id,
            owner,
            error,
            min(300, 30 * 2 ** (job.attempts - 1)),
            settings.max_attempts,
        )
        logger.warning(
            json.dumps(
                {
                    "event": "job_failed",
                    "job_id": job.id,
                    "company_id": job.company_id,
                    "error": error[:500],
                }
            )
        )
    finally:
        stop.set()
        thread.join(timeout=2)
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stop = threading.Event()

    def scheduler():
        while not stop.is_set():
            try:
                schedule()
            except Exception:
                logger.exception("scheduler_failed")
            stop.wait(60)

    scheduler_thread = threading.Thread(target=scheduler, daemon=True)
    scheduler_thread.start()
    while True:
        try:
            if not process_once():
                time.sleep(2)
        except KeyboardInterrupt:
            stop.set()
            scheduler_thread.join(timeout=2)
            break
        except Exception:
            logger.exception("worker_loop_failed")
            time.sleep(5)


if __name__ == "__main__":
    main()
