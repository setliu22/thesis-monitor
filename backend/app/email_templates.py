"""Plain-language text for alert and calendar reminder emails."""

from datetime import date
from decimal import Decimal, InvalidOperation

METRIC_NAMES = {
    "revenue": "Revenue",
    "revenue_growth": "Revenue growth",
    "operating_income": "Operating income",
    "operating_margin": "Operating margin",
    "net_income": "Net income",
    "diluted_eps": "Diluted EPS",
    "cash": "Cash and equivalents",
    "assets": "Total assets",
    "liabilities": "Total liabilities",
    "equity": "Equity",
    "operating_cash_flow": "Operating cash flow",
    "cash_flow_growth": "Cash flow growth",
    "capital_expenditures": "Capital expenditures",
    "free_cash_flow": "Free cash flow",
    "debt": "Long-term debt",
}

OPERATORS = {
    "lt": "below",
    "lte": "at or below",
    "gt": "above",
    "gte": "at or above",
}


def _decimal(value):
    try:
        return Decimal(str(value)) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


def _trimmed(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _money(value):
    number = _decimal(value)
    if number is None:
        return "unavailable"
    sign = "-" if number < 0 else ""
    number = abs(number)
    for scale, suffix in (
        (Decimal(1000000000000), "T"),
        (Decimal(1000000000), "B"),
        (Decimal(1000000), "M"),
    ):
        if number >= scale:
            compact = (number / scale).quantize(Decimal("0.01"))
            return f"{sign}${compact:.2f}{suffix}"
    return f"{sign}${number:,.2f}".rstrip("0").rstrip(".")


def _display_number(value, unit):
    number = _decimal(value)
    if number is None:
        return "unavailable"
    if unit == "%":
        return f"{_trimmed(number.quantize(Decimal('0.1')))}%"
    if unit == "USD":
        return _money(number)
    if unit == "USD/share":
        return f"${number.quantize(Decimal('0.01')):,.2f} per share"
    return _trimmed(number)


def _date(value):
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return "date unavailable"
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


def _period(start, end):
    try:
        start_date = date.fromisoformat(str(start)[:10])
        end_date = date.fromisoformat(str(end)[:10])
    except (TypeError, ValueError):
        return _date(end)
    first = f"{start_date.strftime('%b')} {start_date.day}"
    if start_date.year == end_date.year:
        return f"{first}–{_date(end)}"
    return f"{_date(start)}–{_date(end)}"


def _comparison_lines(evidence, metric_name):
    sources = evidence.get("sources")
    if evidence.get("derivation") != "year_over_year" or not isinstance(sources, list):
        return []
    current_end = evidence.get("end")
    current = next(
        (item for item in sources if item.get("end") == current_end), None
    )
    prior = next((item for item in sources if item is not current), None)
    if not current or not prior:
        return []
    base_name = metric_name.removesuffix(" growth")
    lines = [
        f"{base_name} comparison:",
        f"This quarter: {_display_number(current.get('value'), current.get('unit', 'USD'))}",
        f"Same quarter last year: {_display_number(prior.get('value'), prior.get('unit', 'USD'))}",
    ]
    filings = sorted(
        {
            (item.get("form"), item.get("filed"))
            for item in (current, prior)
            if item.get("form") and item.get("filed")
        }
    )
    if filings:
        form, filed = filings[0]
        lines.append(f"SEC {form} filed {_date(filed)}")
    return lines


def alert_email_content(company, alert, app_origin=""):
    evidence = alert.evidence or {}
    metric = evidence.get("metric", "")
    metric_name = METRIC_NAMES.get(metric, metric.replace("_", " ").capitalize() or "Metric")
    unit = evidence.get(
        "unit", "%" if metric.endswith(("_growth", "_margin")) else "USD"
    )
    operator = OPERATORS.get(evidence.get("operator"), "at")
    value = _display_number(evidence.get("value"), unit)
    threshold = _display_number(evidence.get("threshold"), unit)

    if evidence.get("operator") in OPERATORS and evidence.get("threshold") is not None:
        condition = f"{operator} {threshold}"
        subject = f"{company.ticker} alert: {metric_name} {condition}"
        summary = f"{metric_name} was {value}, {operator} your threshold of {threshold}."
    else:
        condition = ""
        subject = f"{company.ticker} monitoring alert"
        summary = f"A monitoring alert was triggered for {metric_name.lower()}. Latest value: {value}."

    lines = [
        f"{company.ticker} ({company.name}) — {metric_name}",
        "",
        summary,
    ]
    if evidence.get("start"):
        lines.append(f"Period: {_period(evidence.get('start'), evidence.get('end'))}")
    elif evidence.get("end"):
        lines.append(f"As of: {_date(evidence.get('end'))}")

    rule_name = str(evidence.get("rule_name", "")).strip()
    rule_name_threshold = _decimal(rule_name)
    threshold_value = _decimal(evidence.get("threshold"))
    if rule_name and rule_name.casefold() not in {
        str(evidence.get("threshold", "")).strip().casefold(),
        metric.replace("_", " ").casefold(),
        f"{metric.replace('_', ' ')} {condition}".strip().casefold(),
    } and not (
        rule_name_threshold is not None
        and threshold_value is not None
        and rule_name_threshold == threshold_value
    ):
        lines.append(f"Rule: {rule_name}")

    lines.extend(_comparison_lines(evidence, metric_name))
    if app_origin:
        lines.extend(["", f"Open this alert in Thesis Monitor: {app_origin}"])
    return subject[:250], "Thesis Monitor alert\n\n" + "\n".join(lines)


def event_reminder_email_content(event, lead, app_origin=""):
    unit = "day" if lead == 1 else "days"
    subject = f"Reminder: {event.title} in {lead} {unit}"[:250]
    lines = [
        "Upcoming calendar event",
        "",
        f"Event: {event.title}",
        f"Date: {_date(event.day)}",
        f"Reminder: {lead} {unit} before",
    ]
    if event.status == "estimated":
        label = "earnings date" if event.category == "earnings" else "event date"
        lines.append(f"This {label} is estimated and may change.")
    if app_origin:
        lines.extend(["", f"Open your investment calendar: {app_origin}"])
    return subject, "\n".join(lines)
