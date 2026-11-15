"""Earnings-driven refresh: confirmed issuer dates or an explicit estimate window."""

import re
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from .models import Company, Filing, Observation
from .db import SessionLocal

CACI_HOME = "https://investor.caci.com/"
MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        1,
    )
}


def release_date(html, publication):
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    match = re.search(
        r"will release its financial results.{0,300}?(?:Monday|Tuesday|Wednesday|Thursday|Friday),?\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan\.|Feb\.|Mar\.|Apr\.|Aug\.|Sep\.|Oct\.|Nov\.|Dec\.)\s+(\d{1,2})",
        text,
        re.I,
    )
    if not match:
        return None
    month = next(
        (n for m, n in MONTHS.items() if m.startswith(match[1].lower().rstrip("."))),
        None,
    )
    for year in (publication.year, publication.year + 1):
        try:
            candidate = date(year, month, int(match[2]))
        except (ValueError, TypeError):
            continue
        if publication <= candidate <= publication + timedelta(days=90):
            return candidate
    return None


def caci_calendar(client):
    response = client.get(CACI_HOME + "news?l=100")
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    for a in soup.select("a[href]"):
        url = urljoin(CACI_HOME, a["href"]).split("?")[0]
        path = urlparse(url)
        if path.scheme != "https" or path.hostname != "investor.caci.com":
            continue
        match = re.match(r"/(\d{4}-\d{2}-\d{2})-CACI-Schedules-", path.path)
        if match and url not in [u for _, u in candidates]:
            candidates.append((date.fromisoformat(match[1]), url))
    dates = []
    for publication, url in sorted(candidates, reverse=True)[:2]:
        response = client.get(url)
        response.raise_for_status()
        day = release_date(response.text, publication)
        if day:
            dates.append((day, url))
    return max(dates, default=None)


def update_calendar(sessions=SessionLocal, client=None, current=None):
    current = current or datetime.now(timezone.utc)
    with sessions() as s:
        targets = [
            (c.id, c.cik, dict(c.earnings_schedule or {}))
            for c in s.scalars(select(Company))
        ]
    for identity, cik, state in targets:
        checked = state.get("checked_at")
        if checked and current - datetime.fromisoformat(checked) < timedelta(days=1):
            continue
        result, error = None, None
        if int(cik) == 16058:
            try:
                if client:
                    result = caci_calendar(client)
                else:
                    with httpx.Client(
                        timeout=15,
                        follow_redirects=False,
                        headers={"User-Agent": "ThesisMonitor/1.0 earnings calendar"},
                    ) as http:
                        result = caci_calendar(http)
            except (httpx.HTTPError, ValueError):
                error = "Calendar lookup failed; using the estimated reporting window."
        with sessions.begin() as s:
            company = s.scalar(
                select(Company).where(Company.id == identity).with_for_update()
            )
            if not company:
                continue
            state = dict(company.earnings_schedule or {})
            state["checked_at"] = current.isoformat()
            state["error"] = error
            filing = latest_loaded_report(s, identity)
            filed = date.fromisoformat(filing.filed) if filing else None
            if (
                result
                and result[0] >= current.date() - timedelta(days=30)
                and (not filed or filed < result[0] - timedelta(days=14))
            ):
                state.update(
                    date=result[0].isoformat(), status="confirmed", source=result[1]
                )
            elif filed and (
                not state.get("date")
                or filed >= date.fromisoformat(state["date"]) - timedelta(days=14)
                or date.fromisoformat(state["date"])
                < current.date() - timedelta(days=30)
            ):
                state.update(
                    date=(filed + timedelta(days=91)).isoformat(),
                    status="estimated",
                    source="Prior SEC quarterly/annual filing date + 91 days",
                )
            company.earnings_schedule = state


def refresh_due(company, current, latest_filing=None):
    if not company.last_success:
        return True
    state = company.earnings_schedule or {}
    if not state.get("date"):
        return False
    day = date.fromisoformat(state["date"])
    confirmed = state.get("status") == "confirmed"
    start = datetime.combine(day, datetime.min.time(), ZoneInfo("America/New_York"))
    start += timedelta(hours=16, minutes=30) if confirmed else -timedelta(days=14)
    end = start + timedelta(days=30 if confirmed else 44)
    if not start <= current <= end:
        return False
    # The new quarterly filing ends this earnings cycle, even if the calendar is unchanged.
    if latest_filing and date.fromisoformat(latest_filing.filed) >= day - timedelta(
        days=14
    ):
        return False
    last = company.last_attempt or company.last_success
    return not last or current - datetime.fromisoformat(last) >= timedelta(days=1)


def latest_loaded_report(session, company_id):
    # A submissions entry can precede its companyfacts data. Keep polling until both exist.
    loaded = (
        select(Observation.id)
        .where(
            Observation.company_id == Filing.company_id,
            Observation.period_end == Filing.report_date,
            Observation.metric == "revenue",
            Observation.active.is_(True),
        )
        .exists()
    )
    return session.scalar(
        select(Filing)
        .where(
            Filing.company_id == company_id, Filing.form.in_(["10-Q", "10-K"]), loaded
        )
        .order_by(Filing.filed.desc())
        .limit(1)
    )
