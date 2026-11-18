"""Wake bounded queue processing on user activity; SQL leases arbitrate workers.

The hosted free web service needs no extra worker subscription. Periodic GitHub
runs still recover persisted work when the web service sleeps.
"""

import logging
import threading
import time
from sqlalchemy import select, and_, or_
from .config import settings
from .db import SessionLocal
from .models import Job, now

_gate = threading.Lock()
logger = logging.getLogger(__name__)


def wake_analysis():
    if not settings.groq_api_key or not _gate.acquire(blocking=False):
        return
    try:
        with SessionLocal() as session:
            queued = session.scalar(
                select(Job.id)
                .where(
                    Job.kind == "analysis",
                    or_(
                        and_(Job.status == "queued", Job.available_at <= now()),
                        and_(Job.status == "running", Job.lease_until < now()),
                    ),
                )
                .limit(1)
            )
        if queued is None:
            _gate.release()
            return
        thread = threading.Thread(target=_drain, name="analysis-queue", daemon=True)
        thread.start()
    except Exception:
        _gate.release()
        logger.exception("analysis_dispatch_failed")


def _drain():
    from .worker import process_once

    deadline = time.monotonic() + 600
    try:
        while time.monotonic() < deadline:
            if process_once(SessionLocal, kind="analysis"):
                continue
            with SessionLocal() as session:
                due = session.scalar(
                    select(Job.available_at)
                    .where(Job.kind == "analysis", Job.status == "queued")
                    .order_by(Job.available_at)
                    .limit(1)
                )
            if not due:
                return
            from datetime import datetime, timezone

            wait = max(
                1,
                (
                    datetime.fromisoformat(due) - datetime.now(timezone.utc)
                ).total_seconds(),
            )
            if wait > deadline - time.monotonic():
                return
            time.sleep(min(15, wait))
    except Exception:
        logger.exception("analysis_dispatch_worker_failed")
    finally:
        _gate.release()
