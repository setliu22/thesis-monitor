"""Finite background run for hosted schedulers, independent of web traffic."""

import logging
import time

from .config import settings
from .db import SessionLocal
from .notifications import configured, deliver_once, reconcile_once
from .worker import process_once, schedule

logger = logging.getLogger("thesis.scheduled")


def drain_notifications():
    if not configured():
        return
    started = time.monotonic()
    sends = receipts = 0
    for _ in range(100):
        if time.monotonic() - started >= 120:
            break
        sent = deliver_once(SessionLocal)
        checked = reconcile_once(SessionLocal)
        sends += int(sent)
        receipts += int(checked)
        if not sent and not checked:
            break
        time.sleep(1)
    logger.info("notification_batch_complete sends=%s receipts=%s", sends, receipts)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not settings.database_url or not settings.sec_user_agent:
        raise RuntimeError("DATABASE_URL and SEC_USER_AGENT must be configured")
    # Email is optional; discovery and narrative reviews must run unattended.

    started = time.monotonic()
    # Existing outbox work gets its own budget before slow ingestion begins.
    drain_notifications()
    schedule(SessionLocal)
    drain_notifications()
    jobs = 0
    # Do not wait for retries scheduled in the future: the next run recovers them.
    while jobs < 20 and time.monotonic() - started < 480:
        # Data refreshes get priority over optional model work in this finite run.
        if not (
            process_once(SessionLocal, kind="refresh")
            or process_once(SessionLocal, kind="analysis")
        ):
            break
        jobs += 1
    drain_notifications()
    logger.info("scheduled_run_complete jobs=%s", jobs)


if __name__ == "__main__":
    main()
