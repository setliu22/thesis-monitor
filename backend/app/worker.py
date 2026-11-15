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
from .config import settings
from .db import SessionLocal, sec_gate
from .models import Company
from .sec import SecClient, valid_identity
from .jobs import enqueue_refresh, claim_job, heartbeat, finish_job, fail_job
from .ingest import ingest_company

logger = logging.getLogger("thesis.worker")


def schedule(sessions=SessionLocal):
    if not valid_identity(settings.sec_user_agent):
        return
    with sessions.begin() as s:
        for company in s.scalars(select(Company)):
            last = company.last_attempt or company.created_at
            if (
                datetime.now(timezone.utc) - datetime.fromisoformat(last)
            ).total_seconds() >= settings.refresh_seconds:
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
        finish_job(sessions, job.id, owner)
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
        fail_job(
            sessions,
            job.id,
            owner,
            str(exc),
            min(300, 30 * 2 ** (job.attempts - 1)),
            settings.max_attempts,
        )
        logger.warning(
            json.dumps(
                {
                    "event": "job_failed",
                    "job_id": job.id,
                    "company_id": job.company_id,
                    "error": str(exc)[:500],
                }
            )
        )
    finally:
        stop.set()
        thread.join(timeout=2)
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    while True:
        try:
            schedule()
            if not process_once():
                time.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception:
            logger.exception("worker_loop_failed")
            time.sleep(5)


if __name__ == "__main__":
    main()
