"""Adapters for published schedules. No inferred market moves or fabricated dates."""

import calendar
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
import httpx
from bs4 import BeautifulSoup
from .feed_cache import FeedError

FED = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS = "https://www.bls.gov/schedule/news_release/bls.ics"
BEA = "https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics"
ELECTION_SOURCE = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title2-section7&num=0&edition=prelim"


def fetch(url):
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise FeedError(
                        f"Source unavailable (HTTP {response.status_code}); cached events are retained."
                    )
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 5_000_000:
                        raise FeedError("Source exceeded the response limit.")
        return data.decode("utf-8-sig")
    except (httpx.HTTPError, UnicodeError):
        raise FeedError("Source request failed; cached events are retained.") from None


def fed_events():
    soup = BeautifulSoup(fetch(FED), "html.parser")
    result = []
    for panel in soup.select(".panel"):
        heading = panel.find(["h4", "h3"])
        match = re.search(
            r"(\d{4}) FOMC Meetings",
            heading.get_text(" ", strip=True) if heading else "",
        )
        if not match:
            continue
        year = int(match[1])
        for i, meeting in enumerate(panel.select(".fomc-meeting")):
            monthnode = meeting.select_one(".fomc-meeting__month")
            datenode = meeting.select_one(".fomc-meeting__date")
            if not monthnode or not datenode:
                continue
            months = [m for m in monthnode.get_text(" ", strip=True).split("/") if m]
            month = next(
                (
                    n
                    for n in range(1, 13)
                    if calendar.month_name[n].lower() == months[-1].strip().lower()
                ),
                None,
            )
            days = re.findall(r"\d+", datenode.get_text(" ", strip=True))
            if not month or not days:
                continue
            try:
                day = date(year, month, int(days[-1])).isoformat()
            except ValueError:
                continue
            result.append(
                dict(
                    key=f"fed:{year}:{i}",
                    category="fed",
                    title="FOMC meeting concludes",
                    day=day,
                    starts_at=None,
                    source_url=FED,
                    status="scheduled",
                    notes="Published Federal Reserve meeting schedule. A meeting does not guarantee a rate change.",
                )
            )
    if not result:
        raise FeedError(
            "The Federal Reserve schedule format changed; cached dates are retained."
        )
    return {"events": result}


def clean_ics(value):
    return (
        value.replace("\\n", " ")
        .replace("\\N", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def parse_ics(text, source, provider):
    unfolded = re.sub(r"\r?\n[ \t]", "", text)
    results = []
    for block in unfolded.split("BEGIN:VEVENT")[1:]:
        fields = {}
        params = {}
        for line in block.split("END:VEVENT")[0].splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            name = key.split(";")[0]
            fields[name] = value
            params[name] = key
        title = clean_ics(fields.get("SUMMARY", ""))
        lower = title.lower()
        if provider == "bea" and not (
            lower.startswith("gross domestic product")
            or lower.startswith("gdp (")
            or lower.startswith("personal income and outlays")
        ):
            continue
        category = (
            "inflation"
            if any(
                x in lower
                for x in [
                    "consumer price",
                    "producer price",
                    "personal income",
                    "personal consumption",
                ]
            )
            else "employment"
            if any(x in lower for x in ["employment situation", "job openings"])
            else "gdp"
            if "gross domestic product" in lower or "gdp" in lower
            else None
        )
        if not category or fields.get("STATUS") == "CANCELLED":
            continue
        raw = fields.get("DTSTART", "")
        try:
            if len(raw) == 8:
                day = datetime.strptime(raw, "%Y%m%d").date().isoformat()
                starts = None
            else:
                dt = datetime.strptime(raw.rstrip("Z"), "%Y%m%dT%H%M%S")
                match = re.search(r"TZID=([^;:]+)", params.get("DTSTART", ""))
                tz = (
                    timezone.utc
                    if raw.endswith("Z")
                    else ZoneInfo(
                        match[1].replace("US-Eastern", "America/New_York")
                        if match
                        else "America/New_York"
                    )
                )
                dt = dt.replace(tzinfo=tz)
                starts = dt.astimezone(timezone.utc).isoformat()
                day = dt.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        except (ValueError, KeyError):
            continue
        uid = fields.get("UID") or f"{title}:{day}"
        results.append(
            dict(
                key=f"{provider}:{uid}"[:250],
                category=category,
                title=title[:250],
                day=day,
                starts_at=starts,
                source_url=source,
                status="scheduled",
                notes=clean_ics(fields.get("DESCRIPTION", ""))[:3000],
            )
        )
    if "BEGIN:VCALENDAR" not in text:
        raise FeedError("Source did not return a calendar.")
    return {"events": results}


def bls_events():
    return parse_ics(fetch(BLS), BLS, "bls")


def bea_events():
    return parse_ics(fetch(BEA), BEA, "bea")


def election_events():
    # Statutory recurring schedule, not an estimate or a hardcoded election date.
    current = date.today().year
    result = []
    for year in range(current - 2, current + 7):
        if year % 2:
            continue
        first = date(year, 11, 1)
        monday = 1 + (0 - first.weekday()) % 7
        day = date(year, 11, monday + 1)
        result.append(
            dict(
                key=f"election:{year}",
                category="election",
                title="US midterm elections"
                if year % 4
                else "US presidential and congressional elections",
                day=day.isoformat(),
                starts_at=None,
                source_url=ELECTION_SOURCE,
                status="statutory",
                notes="Regular federal Election Day: Tuesday after the first Monday in November in even-numbered years. This is a known date, not a prediction of market direction.",
            )
        )
    return {"events": result}
