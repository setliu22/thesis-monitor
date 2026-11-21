"""Atomic filing discovery and bounded submissions-only safety net."""

from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from .models import CalendarCache, Company, Filing
from .reviews import (
    AUTO_FORMS, earnings_period, latest_filing, recent_earnings_periods, request_review,
)
from .config import settings


def persist_discovery(s, company, submissions):
    """Caller holds the company lock; no commits or company-facts dependency."""
    key = f"discovery-baseline:{company.id}"
    baseline = s.scalar(
        select(CalendarCache).where(CalendarCache.provider == key).with_for_update()
    )
    first = baseline is None
    if first:
        baseline = CalendarCache(provider=key, payload={})
        s.add(baseline)
    recent = submissions.get("filings", {}).get("recent", {})
    known = set(
        s.scalars(select(Filing.accession).where(Filing.company_id == company.id))
    )
    added = []
    for i, accession in enumerate(recent.get("accessionNumber", [])):
        form = recent["form"][i]
        if accession in known or form not in (*AUTO_FORMS, "8-K", "10-Q/A", "10-K/A"):
            continue
        filing = Filing(
            company_id=company.id,
            accession=accession,
            form=form,
            filed=recent["filingDate"][i],
            report_date=(recent.get("reportDate") or [""] * len(recent["form"]))[i],
            document=recent["primaryDocument"][i],
        )
        s.add(filing)
        added.append(filing)
        known.add(accession)
    s.flush()
    baseline.payload = dict(baseline.payload or {}) | {"initialized": True}
    recent_periods = recent_earnings_periods(s, company.id)
    candidates = [
        f for f in added
        if f.form in AUTO_FORMS and earnings_period(f) in recent_periods
    ]
    if first:
        # Existing rows may predate the first release of automatic reviews.
        latest = latest_filing(s, company.id)
        candidates = [latest] if latest else []
    for filing in candidates:
        try:
            request_review(s, company.id, filing.id)
        except ValueError:
            # Remember a missed new report even if old reviews already exist.
            baseline.payload = dict(baseline.payload or {}) | {"review_recovery": True}
    return added


def submissions_only(sessions, client=None, current=None, limit=10):
    """Daily cached discovery independent of earnings windows and facts refreshes."""
    from .db import sec_gate
    from .sec import SecClient, SecError
    from .feed_cache import cached_feed, FeedError

    current = current or datetime.now(timezone.utc)
    if client is None:
        client = SecClient(settings.sec_user_agent, gate=sec_gate)
    # Pick least recently checked first so the bounded runner cannot starve a list.
    with sessions() as s:
        companies = s.scalars(select(Company).where(Company.watched.is_(True))).all()
        due = []
        for company in companies:
            cache = s.scalar(
                select(CalendarCache).where(
                    CalendarCache.provider == f"sec-submissions:{company.id}"
                )
            )
            attempt = (
                datetime.fromisoformat(cache.last_attempt)
                if cache and cache.last_attempt
                else None
            )
            interval = timedelta(hours=1 if cache and cache.error else 24)
            if not attempt or current - attempt >= interval:
                due.append(
                    (
                        cache.last_attempt if cache and cache.last_attempt else "",
                        company.id,
                        company.cik,
                    )
                )
    count = 0
    for _, cid, cik in sorted(due)[:limit]:

        def load():
            try:
                return client.fetch_json(f"/submissions/CIK{cik}.json")
            except SecError as exc:
                raise FeedError(str(exc)) from exc

        data, error = cached_feed(
            f"sec-submissions:{cid}", load, hours=24, sessions=sessions
        )
        if error or not data:
            continue
        with sessions.begin() as s:
            company = s.scalar(
                select(Company).where(Company.id == cid).with_for_update()
            )
            if company and company.watched:
                persist_discovery(s, company, data)
                count += 1
    return count
