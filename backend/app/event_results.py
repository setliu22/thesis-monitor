"""Persist release-date vintages and factual comparisons for calendar events."""

import csv
import io
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
import httpx
from sqlalchemy import select
from .db import SessionLocal
from .models import MarketEvent, Company, Observation, Filing, now
from .feed_cache import cached_feed, FeedError

ALFRED = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
RATE_CONTEXT = "Higher rates can raise new borrowing and refinancing costs and reduce the present value of distant cash flows. Lower rates can ease financing conditions. Fixed-rate debt may not reprice immediately; rates alone do not determine which stock to buy."
CONTEXT_SOURCE = "https://www.federalreserve.gov/faqs/money_12856.htm"


def series_for(event):
    title = event.title.lower()
    if event.category == "fed":
        return ["DFEDTARU", "DFEDTARL"]
    if "consumer price" in title:
        return ["CPIAUCSL"]
    if "producer price" in title:
        return ["PPIFIS"]
    if title.startswith(("gross domestic product", "gdp (")):
        return ["A191RL1Q225SBEA"]
    if "personal income" in title or "personal consumption" in title:
        return ["PCEPI"]
    if "job openings" in title:
        return ["JTSJOL"]
    if "employment situation" in title:
        return ["PAYEMS", "UNRATE"]
    return []


def parse_vintage(text, series, vintage):
    reader = csv.DictReader(io.StringIO(text))
    if (
        not reader.fieldnames
        or len(reader.fieldnames) != 2
        or reader.fieldnames[0] != "observation_date"
    ):
        raise ValueError("Historical data did not confirm its vintage")
    column = reader.fieldnames[1]
    match = re.fullmatch(re.escape(series) + r"_(\d{8})", column)
    if not match:
        raise ValueError("Historical data did not confirm its vintage")
    actual_vintage = datetime.strptime(match[1], "%Y%m%d").date().isoformat()
    if actual_vintage > vintage:
        raise ValueError("Historical data contains a later vintage")
    values = {}
    for row in reader:
        try:
            day = date.fromisoformat(row["observation_date"]).isoformat()
            value = Decimal(row[column])
            if value.is_finite() and day <= actual_vintage:
                values[day] = str(value)
        except (ValueError, InvalidOperation, TypeError):
            continue
    return [{"date": d, "value": values[d]} for d in sorted(values)][-18:]


def vintage_data(series, vintage, sessions):
    def load():
        try:
            with httpx.Client(timeout=20, follow_redirects=False) as client:
                with client.stream(
                    "GET", ALFRED, params={"id": series, "vintage_date": vintage}
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for part in response.iter_bytes():
                        body.extend(part)
                        if len(body) > 2_000_000:
                            raise FeedError("Historical series exceeds size limit")
            return {
                "values": parse_vintage(body.decode("utf-8-sig"), series, vintage),
                "series": series,
                "vintage": vintage,
            }
        except (httpx.HTTPError, ValueError, UnicodeError):
            raise FeedError(
                "Historical result source unavailable; saved outcomes retained"
            ) from None

    payload, error = cached_feed(
        f"actual:{series}:{vintage}",
        load,
        hours=1
        if date.fromisoformat(vintage)
        >= datetime.now(ZoneInfo("America/New_York")).date() - timedelta(days=3)
        else 24 * 365,
        sessions=sessions,
    )
    if error or "values" not in payload:
        raise FeedError(error or "Historical result is not available yet")
    return payload["values"]


def metric(label, value, previous, unit, period, previous_period):
    value, previous = Decimal(value), Decimal(previous)
    delta = value - previous
    return {
        "label": label,
        "value": str(value),
        "previous": str(previous),
        "change": str(delta),
        "unit": unit,
        "direction": "up" if delta > 0 else "down" if delta < 0 else "unchanged",
        "period": period,
        "previous_period": previous_period,
    }


def month_before(day):
    return (
        (date.fromisoformat(day).replace(day=1) - timedelta(days=1))
        .replace(day=1)
        .isoformat()
    )


def adjacent_months(values, count):
    if len(values) < count:
        return False
    tail = values[-count:]
    return all(
        month_before(tail[i]["date"]) == tail[i - 1]["date"] for i in range(1, count)
    )


def calculate_macro(event, current, before):
    series = series_for(event)
    if not series:
        return {
            "status": "unsupported",
            "reason": "No verified outcome feed is connected for this event type.",
        }
    primary = series[0]
    rows = current.get(primary, [])
    pending = {
        "status": "pending",
        "reason": "Waiting for this release’s historical values.",
    }
    if not rows:
        return pending
    metrics = []
    if primary == "DFEDTARU":
        effective = (date.fromisoformat(event.day) + timedelta(days=1)).isoformat()
        for sid, label in [
            ("DFEDTARU", "Fed target upper limit"),
            ("DFEDTARL", "Fed target lower limit"),
        ]:
            a = next((r for r in current.get(sid, []) if r["date"] == effective), None)
            b = next((r for r in current.get(sid, []) if r["date"] == event.day), None)
            if not a or not b:
                return pending
            metrics.append(
                metric(label, a["value"], b["value"], "%", effective, event.day)
            )
        context = RATE_CONTEXT
    elif primary == "A191RL1Q225SBEA":
        match = re.search(r"([1-4])(?:st|nd|rd|th) Quarter (\d{4})", event.title, re.I)
        if not match or len(rows) < 2:
            return pending
        period = f"{match[2]}-{(int(match[1]) - 1) * 3 + 1:02d}-01"
        index = next((i for i, r in enumerate(rows) if r["date"] == period), None)
        if index is None or index == 0:
            return pending
        a, b = rows[index], rows[index - 1]
        if (
            date.fromisoformat(a["date"]) - date.fromisoformat(b["date"])
        ).days not in range(80, 101):
            return pending
        metrics = [
            metric(
                "Real GDP growth (annualized)",
                a["value"],
                b["value"],
                "%",
                a["date"],
                b["date"],
            )
        ]
        context = "This compares inflation-adjusted growth with the previous quarter, not the prior estimate or market consensus. Faster growth can support demand but can also affect inflation and rate expectations; company exposure differs."
    else:
        previous = before.get(primary, [])
        # Require a newly available reference month; do not attach an older release.
        if not previous or rows[-1]["date"] <= previous[-1]["date"]:
            return pending
        if primary in ("CPIAUCSL", "PPIFIS", "PCEPI"):
            if not adjacent_months(rows, 3):
                return pending
            a, b, c = rows[-1], rows[-2], rows[-3]
            if Decimal(b["value"]) <= 0 or Decimal(c["value"]) <= 0:
                return pending
            current_change = (Decimal(a["value"]) / Decimal(b["value"]) - 1) * 100
            prior_change = (Decimal(b["value"]) / Decimal(c["value"]) - 1) * 100
            label = {
                "CPIAUCSL": "Monthly CPI inflation",
                "PPIFIS": "Monthly producer-price inflation",
                "PCEPI": "Monthly PCE inflation",
            }[primary]
            metrics = [
                metric(label, current_change, prior_change, "%", a["date"], b["date"])
            ]
            context = (
                (
                    "Prices are still rising even if the monthly inflation rate slowed. "
                    if current_change > 0
                    else "The monthly price index fell or was flat. "
                )
                + "Inflation can affect input costs, pricing power and rate expectations. This is a month-to-month comparison, not a stock-price prediction or a consensus surprise."
            )
        elif primary == "PAYEMS":
            if not adjacent_months(rows, 3):
                return pending
            a, b, c = rows[-1], rows[-2], rows[-3]
            metrics = [
                metric(
                    "Payroll jobs added",
                    (Decimal(a["value"]) - Decimal(b["value"])) * 1000,
                    (Decimal(b["value"]) - Decimal(c["value"])) * 1000,
                    "jobs",
                    a["date"],
                    b["date"],
                )
            ]
            unemployment = current.get("UNRATE", [])
            if (
                len(unemployment) >= 2
                and unemployment[-1]["date"] == a["date"]
                and adjacent_months(unemployment, 2)
            ):
                metrics.append(
                    metric(
                        "Unemployment rate",
                        unemployment[-1]["value"],
                        unemployment[-2]["value"],
                        "%",
                        a["date"],
                        b["date"],
                    )
                )
            context = "Payroll additions show hiring momentum; unemployment is a separate measure. Strong hiring can support demand while keeping wage and rate pressures elevated. Weaker hiring can ease those pressures but weaken demand."
        elif primary == "JTSJOL":
            if not adjacent_months(rows, 2):
                return pending
            a, b = rows[-1], rows[-2]
            metrics = [
                metric(
                    "Job openings",
                    Decimal(a["value"]) * 1000,
                    Decimal(b["value"]) * 1000,
                    "jobs",
                    a["date"],
                    b["date"],
                )
            ]
            context = "Openings indicate labor demand, not jobs actually added. Fewer openings can ease hiring and wage pressures, but can also signal softer demand."
    if not metrics:
        return pending
    return {
        "status": "reported",
        "metrics": metrics,
        "direction": metrics[0]["direction"],
        "context": context,
        "context_source": CONTEXT_SOURCE,
        "basis": "Values available on the release-date vintage. Earlier periods include revisions already known on that date; later revisions are excluded.",
    }


def earnings_result(s, event):
    if not event.company_id:
        return {
            "status": "unsupported",
            "reason": "No company is linked to this earnings event.",
        }
    # Only accept a report first filed around this event, never a later quarter.
    expected = getattr(event, "key", "").rsplit(":", 1)[-1]
    try:
        date.fromisoformat(expected)
    except ValueError:
        return {
            "status": "unsupported",
            "reason": "The earnings event has no verified fiscal reference period.",
        }
    report = s.scalar(
        select(Filing)
        .where(
            Filing.company_id == event.company_id,
            Filing.form.in_(["10-K", "10-Q"]),
            Filing.report_date == expected,
            Filing.filed
            >= (date.fromisoformat(event.day) - timedelta(days=14)).isoformat(),
            Filing.filed
            <= (date.fromisoformat(event.day) + timedelta(days=30)).isoformat(),
        )
        .order_by(Filing.filed)
        .limit(1)
    )
    if not report:
        return {
            "status": "pending",
            "reason": "Waiting for the corresponding SEC report and financial data.",
        }
    kind = "annual" if report.form == "10-K" else "quarter"
    rows = list(
        s.scalars(
            select(Observation).where(
                Observation.company_id == event.company_id, Observation.kind == kind
            )
        )
    )
    metrics = []
    for name, label in [
        ("revenue", "Revenue"),
        ("net_income", "Net income"),
        ("diluted_eps", "Diluted EPS"),
    ]:

        def source_rank(row):
            return (
                max(x.get("filed", "") for x in row.payload["sources"]),
                row.payload.get("derivation") == "reported",
                row.identity,
            )

        eligible = [
            r
            for r in rows
            if r.metric == name
            and r.value is not None
            and r.payload.get("sources")
            and all(
                (x.get("filed") or "9999") <= report.filed for x in r.payload["sources"]
            )
        ]
        current_rows = [r for r in eligible if r.period_end == expected]
        current = max(current_rows, key=source_rank) if current_rows else None
        if not current:
            continue

        def duration(row):
            start = row.payload.get("start")
            return (
                (date.fromisoformat(row.period_end) - date.fromisoformat(start)).days
                if start
                else None
            )

        tags = {x["tag"] for x in current.payload["sources"]}
        priors = [
            r
            for r in eligible
            if 350
            <= (
                date.fromisoformat(current.period_end)
                - date.fromisoformat(r.period_end)
            ).days
            <= 380
            and r.unit == current.unit
            and {x["tag"] for x in r.payload["sources"]} == tags
            and duration(r) is not None
            and duration(current) is not None
            and abs(duration(r) - duration(current)) <= 10
        ]
        prior = (
            max(priors, key=lambda r: (r.period_end, source_rank(r)))
            if priors
            else None
        )
        if prior:
            item = metric(
                label,
                current.value,
                prior.value,
                current.unit,
                current.period_end,
                prior.period_end,
            )
            item["sources"] = current.payload.get("sources", []) + prior.payload.get(
                "sources", []
            )
            metrics.append(item)
    if not metrics:
        return {
            "status": "pending",
            "reason": "The report is available, but comparable source values are not loaded.",
        }
    return {
        "status": "reported",
        "metrics": metrics,
        "direction": metrics[0]["direction"],
        "context": "Compared with the same fiscal period a year earlier. This does not establish whether the investment thesis changed or whether results beat expectations.",
        "basis": "SEC report available after the earnings event; values limited to sources filed by that report date.",
        "sources": [
            {
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(s.get(Company, event.company_id).cik)}/{report.accession.replace('-', '')}/{report.document}"
            }
        ],
    }


def refresh_event_results(sessions=SessionLocal, limit=4):
    current = datetime.now(timezone.utc)
    today = current.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    with sessions() as s:
        events = list(
            s.scalars(
                select(MarketEvent).where(
                    MarketEvent.active.is_(True),
                    MarketEvent.day <= today,
                    MarketEvent.day
                    >= (current.date() - timedelta(days=400)).isoformat(),
                )
            )
        )
        due = [
            e
            for e in events
            if (
                (e.outcome or {}).get("status") not in ("reported", "unsupported")
                or (e.outcome or {}).get("provisional")
                or (
                    (e.outcome or {}).get("event_revision")
                    and e.outcome["event_revision"] != e.revision
                )
            )
            and (
                not (e.outcome or {}).get("checked_at")
                or datetime.fromisoformat(e.outcome["checked_at"])
                < current - timedelta(hours=1)
            )
            and (not e.starts_at or datetime.fromisoformat(e.starts_at) <= current)
        ]
        due.sort(
            key=lambda e: (
                (e.outcome or {}).get("checked_at") or "",
                -date.fromisoformat(e.day).toordinal(),
            )
        )
        selected = [
            (e.id, e.category, e.title, e.day, e.company_id, e.revision, e.key)
            for e in due[:limit]
        ]
    for eid, category, title, day, cid, revision, event_key in selected:
        from types import SimpleNamespace

        event = SimpleNamespace(
            id=eid,
            category=category,
            title=title,
            day=day,
            company_id=cid,
            key=event_key,
        )
        try:
            if category == "earnings":
                with sessions() as s:
                    result = earnings_result(s, event)
            else:
                series = series_for(event)
                effective = (
                    (date.fromisoformat(day) + timedelta(days=1)).isoformat()
                    if category == "fed"
                    else day
                )
                if effective > today:
                    result = {
                        "status": "pending",
                        "reason": "Waiting for next-day policy-rate data.",
                    }
                elif not series:
                    result = {
                        "status": "unsupported",
                        "reason": "No verified outcome feed is connected for this event type.",
                    }
                else:
                    values = {
                        sid: vintage_data(sid, effective, sessions) for sid in series
                    }
                    previous = (
                        {
                            sid: vintage_data(
                                sid,
                                (
                                    date.fromisoformat(day) - timedelta(days=1)
                                ).isoformat(),
                                sessions,
                            )
                            for sid in series[:1]
                        }
                        if category != "fed"
                        else {}
                    )
                    result = calculate_macro(event, values, previous)
                    result["provisional"] = effective >= today
                    result["sources"] = [
                        {
                            "series": sid,
                            "vintage": effective,
                            "url": f"https://alfred.stlouisfed.org/series?seid={sid}&vintage_date={effective}",
                        }
                        for sid in series
                    ]
            result["checked_at"] = now()
            result["event_revision"] = revision
        except FeedError as exc:
            result = {
                "status": "pending",
                "reason": str(exc),
                "checked_at": now(),
                "event_revision": revision,
            }
        with sessions.begin() as s:
            row = s.get(MarketEvent, eid, with_for_update=True)
            if row and row.revision == revision:
                existing = row.outcome or {}
                if (
                    existing.get("status") == "reported"
                    and not existing.get("provisional")
                    and existing.get("event_revision") == revision
                ):
                    continue
                row.outcome = result


def _inflation_index(label):
    label = label.lower()
    if "producer" in label:
        return "ppi"
    if "cpi" in label or "pce" in label:
        return "consumer"
    return None


def metric_explanation(category, metric):
    """Plain-language context for one result metric, without a stock verdict."""
    label = str(metric.get("label", "")).lower()
    direction = metric.get("direction")
    if category == "fed":
        if direction == "unchanged":
            return "The Fed held its target rate steady."
        if direction == "up":
            return "Higher rates could make new borrowing and refinancing more expensive."
        return "Lower rates could make new borrowing and refinancing cheaper."
    if category == "inflation":
        index = _inflation_index(label)
        if index == "consumer":
            return {
                "up": "Faster inflation could squeeze household budgets and curb discretionary spending.",
                "down": "Slower inflation could ease pressure on household budgets and support spending.",
                "unchanged": "Steady inflation could still squeeze budgets if prices outpace incomes.",
            }.get(direction, "Consumer prices help explain how much households can afford and what they may buy.")
        if index == "ppi":
            return {
                "up": "Faster growth in selling prices could help margins if costs rise more slowly.",
                "down": "Slower growth in selling prices could squeeze margins if costs keep rising.",
                "unchanged": "Steady selling-price growth could still squeeze margins if costs accelerate.",
            }.get(direction, "Final-demand PPI tracks selling prices producers receive. Margins depend on how those prices move relative to costs.")
        return "Inflation can affect purchasing power and business costs."
    if "gdp" in label:
        return {
            "up": "Stronger economic growth could support customer demand.",
            "down": "Slower economic growth could soften customer demand.",
        }.get(direction, "Economic growth held its pace.")
    if "payroll" in label:
        return {
            "up": "Stronger hiring could support consumer spending.",
            "down": "Slower hiring could weigh on consumer spending.",
        }.get(direction, "Payroll gains held their pace.")
    if "unemployment" in label:
        return {
            "up": "Higher unemployment could weigh on consumer spending.",
            "down": "Lower unemployment could support spending and increase wage pressure.",
        }.get(direction, "Unemployment held steady.")
    if "opening" in label:
        return {
            "up": "More job openings could increase competition for workers.",
            "down": "Fewer job openings could ease competition for workers.",
        }.get(direction, "Job openings held steady.")
    return ""


def _result_summary(outcome):
    metrics = outcome.get("metrics", [])
    if not metrics:
        return "The reported result is available."
    words = {"up": "increased", "down": "decreased", "unchanged": "was unchanged"}
    descriptions = []
    for item in metrics:
        label = item.get("label", "The metric")
        verb = words.get(item.get("direction"), "changed")
        unit = item.get("unit", "")
        suffix = "%" if unit == "%" else f" {unit}" if unit else ""
        current = _number_text(item.get("value", ""), unit)
        previous = _number_text(item.get("previous", ""), unit)
        if item.get("direction") == "unchanged":
            descriptions.append(f"{label} {verb} at {current}{suffix}")
        else:
            descriptions.append(
                f"{label} {verb} from {previous}{suffix} to {current}{suffix}"
            )
    return "; ".join(descriptions) + "."


def _number_text(value, unit="", percentage_places=2):
    try:
        number = Decimal(str(value))
        if unit == "%":
            quantum = Decimal(1).scaleb(-percentage_places)
            number = number.quantize(quantum)
        elif unit == "jobs":
            number = number.quantize(Decimal("1"))
        return format(number.normalize(), ",f")
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def _dollars(value):
    for scale, suffix in ((Decimal('1000000000'), 'B'), (Decimal('1000000'), 'M'), (Decimal('1000'), 'K')):
        if abs(value) >= scale:
            return f"${value / scale:.2f}{suffix}"
    return f"${value:,.0f}"


def company_context(event, company, observations, thesis=None, outcome=None):
    """Relate a reported macro result to one selected company using dated SEC facts."""
    if event.category not in ("fed", "inflation", "gdp", "employment"):
        return None
    outcome = outcome or {}
    known = []
    for row in observations:
        sources = row.payload.get("sources", [])
        if (
            row.company_id == company.id
            and row.value is not None
            and row.period_end <= event.day
            and sources
            and all((x.get("filed") or "9999") <= event.day for x in sources)
        ):
            known.append(row)
    latest = {}
    for row in sorted(
        known,
        key=lambda r: (
            r.period_end,
            max(x.get("filed", "") for x in r.payload["sources"]),
        ),
    ):
        if row.metric in ("cash", "debt") and row.kind == "instant":
            latest[row.metric] = row
        if row.metric == "operating_cash_flow" and row.kind == "annual":
            latest[row.metric] = row
        if row.metric in ("revenue_growth", "operating_margin") and row.kind in (
            "quarter",
            "annual",
        ):
            latest[row.metric] = row
    facts = []
    for name in (
        "debt",
        "cash",
        "operating_cash_flow",
        "revenue_growth",
        "operating_margin",
    ):
        row = latest.get(name)
        if row:
            links = []
            for source in row.payload["sources"]:
                accn = source.get("accn", "")
                if re.fullmatch(r"\d{10}-\d{2}-\d{6}", accn):
                    links.append(
                        f"https://www.sec.gov/Archives/edgar/data/{int(company.cik)}/{accn.replace('-', '')}/{accn}-index.html"
                    )
            facts.append(
                {
                    "metric": name,
                    "value": str(row.value),
                    "unit": row.unit,
                    "period": row.period_end,
                    "source_urls": list(dict.fromkeys(links)),
                }
            )

    metrics = outcome.get("metrics") or []
    direction = metrics[0].get("direction") if metrics else None
    debt, cash = latest.get("debt"), latest.get("cash")
    headline = "Company exposure is not established."
    note = ""
    if event.category == "fed":
        headline = {
            "up": "Higher borrowing costs could pressure cash flow.",
            "down": "Lower rates could ease future borrowing costs.",
            "unchanged": "The Fed held its target rate steady.",
        }.get(direction, "The rate change is not available.")
        if debt and cash and debt.period_end == cash.period_end:
            amounts = f"{company.ticker} reported {_dollars(debt.value)} in long-term debt and {_dollars(cash.value)} in cash as of {debt.period_end}."
            if debt.value > cash.value:
                mechanism = {
                    "up": "With debt above cash, more expensive refinancing could reduce cash available for operations and investment.",
                    "down": "With debt above cash, cheaper refinancing could leave more cash available as debt comes due.",
                    "unchanged": "With debt above cash, refinancing costs still matter, but this decision does not change the policy-rate target.",
                }.get(direction, "Debt exceeds cash, so refinancing costs matter.")
            else:
                mechanism = {
                    "up": "Cash covers the reported long-term debt balance, which may reduce reliance on borrowing. Higher rates can also increase returns on cash as deposits and investments reprice.",
                    "down": "Cash covers the reported long-term debt balance, which may reduce the benefit from cheaper borrowing. Lower rates can also reduce returns on cash as investments reprice.",
                    "unchanged": "Cash covers the reported long-term debt balance. This decision adds no new policy-rate change to borrowing costs or cash returns.",
                }.get(direction, "Cash covers the reported long-term debt balance.")
            relation = f"{amounts} {mechanism}"
        else:
            relation = f"For {company.ticker}, rate changes can affect new borrowing, refinancing and the value investors place on future profits."
        note = "The timing depends on debt maturities, fixed versus variable rates, and how cash is invested."
    elif event.category == "inflation":
        index = _inflation_index(metrics[0].get("label", "")) if metrics else None
        if index == "consumer":
            headline = {
                "up": "Faster consumer inflation can stretch household budgets.",
                "down": "Slower consumer inflation can ease pressure on household budgets.",
                "unchanged": "Consumer inflation held its previous pace.",
            }.get(direction, "Consumer prices can shape household spending.")
            relation = (
                f"For {company.ticker}, the connection depends on how much its customers "
                "rely on household spending."
            )
        elif index == "ppi":
            headline = {
                "up": "Producer selling prices rose faster or fell more slowly.",
                "down": "Producer selling prices rose more slowly or fell faster.",
                "unchanged": "Producer selling prices changed at the same pace.",
            }.get(direction, "Producer prices give context for selling prices.")
            relation = (
                f"For {company.ticker}, margins depend on how its own selling prices move "
                "relative to labor and material costs."
            )
        else:
            headline = "Inflation can affect prices and spending."
            relation = f"The broad index does not establish {company.ticker}'s exposure."
    else:
        growth = latest.get("revenue_growth")
        baseline = f"{company.ticker} reported revenue growth of {_number_text(growth.value, '%', 1)}% as of {growth.period_end}. " if growth else f"For {company.ticker}, "
        if event.category == "gdp":
            headline = {"up": "Faster economic growth could support customer demand.", "down": "Slower economic growth could weaken customer demand.", "unchanged": "Economic growth held its previous pace."}.get(direction, "Economic growth affects the demand backdrop.")
            relation = baseline + "Changes in customer spending can affect new orders and sales, especially for businesses tied to the economic cycle."
            note = "Revenue growth alone does not establish how sensitive the company's customers are to the economy."
        else:
            headline = "Hiring and wage pressure can move in different directions."
            relation = baseline + "Stronger hiring can support customer spending but increase competition for employees. Weaker hiring can ease wage pressure while weakening demand."
            note = "Payrolls, unemployment and job openings measure different things; their effects depend on the company's customers and staffing needs."

    link = None
    if thesis:
        terms = (
            ("debt", "borrow", "financ", "rate")
            if event.category in ("fed", "inflation")
            else ("demand", "growth", "customer", "contract", "hiring")
        )
        link = next(
            (
                sentence
                for sentence in re.split(r"(?<=[.!?])\s+|\n+", thesis.body)
                if any(t in sentence.lower() for t in terms)
            ),
            None,
        )
    return {
        "ticker": company.ticker,
        "headline": headline,
        "relation": relation,
        "note": note,
        "facts": facts,
        "basis": "SEC sources filed on or before the event date.",
        "thesis_link": link,
        "thesis_basis": "Current saved thesis, not a historical recommendation."
        if link
        else None,
    }
