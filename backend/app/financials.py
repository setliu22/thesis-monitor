"""Duration-aware financial normalization. All arithmetic uses Decimal.

Only compatible tags are compared over time; unknown facts remain unavailable.
Source facts are retained in each observation, including derived quarters.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json

TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "diluted_eps": ["EarningsPerShareDiluted"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capital_expenditures": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
}
INSTANT_TAGS = {
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ],
}
INSTANT_METRICS = set(INSTANT_TAGS) | {"debt"}

METRICS = {
    "revenue": "USD",
    "net_income": "USD",
    "diluted_eps": "USD/share",
    "cash": "USD",
    "assets": "USD",
    "liabilities": "USD",
    "equity": "USD",
    "operating_income": "USD",
    "operating_cash_flow": "USD",
    "capital_expenditures": "USD",
    "free_cash_flow": "USD",
    "debt": "USD",
    "revenue_growth": "%",
    "operating_margin": "%",
    "cash_flow_growth": "%",
}


def identity(payload: dict) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def observation(
    metric, start, end, kind, value, sources, derivation="reported", reason=None
):
    result = dict(
        metric=metric,
        start=start,
        end=end,
        kind=kind,
        value=str(value) if value is not None else None,
        unit=METRICS[metric],
        sources=sources,
        derivation=derivation,
        unavailable_reason=reason,
    )
    result["identity"] = identity(result)
    return result


def source(tag, f):
    note = (
        {
            "mapping_note": "Broader capex definition: includes property, plant and equipment, software, and other intangible assets."
        }
        if tag == "PaymentsToAcquireProductiveAssets"
        else {}
    )
    return (
        note
        | {k: f.get(k) for k in ("start", "end", "filed", "accn", "form")}
        | {
            "tag": tag,
            "unit": "USD/share" if tag == "EarningsPerShareDiluted" else "USD",
            "value": str(f["val"]),
        }
    )


def compatible(a, b):
    return {x["tag"] for x in a["sources"]} == {x["tag"] for x in b["sources"]}


def normalize(companyfacts: dict, as_of: datetime | None = None) -> list[dict]:
    cutoff = (as_of or datetime.now(timezone.utc)).date().isoformat()
    tags = companyfacts.get("facts", {}).get("us-gaap", {})
    output = []
    series = {}
    mappings = {metric: list(names) for metric, names in TAGS.items()}
    for metric, names in mappings.items():
        candidates = {}
        for priority, tag in enumerate(names):
            facts = [
                f
                for f in tags.get(tag, {})
                .get("units", {})
                .get("USD/shares" if metric == "diluted_eps" else "USD", [])
                if f.get("start")
                and f.get("end")
                and f.get("filed", "9999") <= cutoff
                and f.get("form") in ("10-K", "10-Q", "10-K/A", "10-Q/A")
            ]
            # Choose the latest filed version of a fact for each duration.
            latest = {}
            for f in sorted(facts, key=lambda x: (x["filed"], x.get("accn", ""))):
                latest[(f["start"], f["end"])] = f
            for (start, end), f in latest.items():
                duration = days(start, end)
                kind = (
                    "quarter"
                    if 70 <= duration <= 110
                    else "annual"
                    if 330 <= duration <= 380
                    else None
                )
                if kind:
                    key = (start, end, kind)
                    o = observation(
                        metric,
                        start,
                        end,
                        kind,
                        Decimal(str(f["val"])),
                        [source(tag, f)],
                    )
                    rank = (-priority, f["filed"], True, f.get("accn", ""))
                    if key not in candidates or rank > candidates[key][0]:
                        candidates[key] = (rank, o)
                # Subtract a preceding compatible YTD period, including Q4 from FY.
                if metric != "diluted_eps" and 150 <= duration <= 380:
                    priors = [
                        p
                        for p in facts
                        if p["start"] == start
                        and p["end"] < end
                        and 70 <= days(p["end"], end) - 1 <= 110
                        and p["filed"] <= f["filed"]
                    ]
                    if priors:
                        p = max(
                            priors,
                            key=lambda p: (
                                p["end"],
                                p["accn"] == f["accn"],
                                p["filed"],
                                p.get("accn", ""),
                            ),
                        )
                        qstart = (
                            date.fromisoformat(p["end"]) + timedelta(days=1)
                        ).isoformat()
                        key = (qstart, end, "quarter")
                        o = observation(
                            metric,
                            qstart,
                            end,
                            "quarter",
                            Decimal(str(f["val"])) - Decimal(str(p["val"])),
                            [source(tag, f), source(tag, p)],
                            "ytd_difference",
                        )
                        rank = (-priority, f["filed"], False, f.get("accn", ""))
                        if key not in candidates or rank > candidates[key][0]:
                            candidates[key] = (rank, o)
        series[metric] = [o for _, o in candidates.values()]
        output.extend(series[metric])

    # Derived metrics require matching starts and ends.
    def matching(metric, base):
        return next(
            (
                x
                for x in series.get(metric, [])
                if (x["start"], x["end"], x["kind"])
                == (base["start"], base["end"], base["kind"])
            ),
            None,
        )

    for base in series["revenue"]:
        income = matching("operating_income", base)
        valid = income is not None and Decimal(base["value"]) > 0
        output.append(
            observation(
                "operating_margin",
                base["start"],
                base["end"],
                base["kind"],
                Decimal(income["value"]) / Decimal(base["value"]) * 100
                if valid
                else None,
                base["sources"] + (income["sources"] if income else []),
                "ratio",
                None
                if valid
                else "Matching operating income and positive revenue required",
            )
        )
    for base in series["operating_cash_flow"]:
        capex = matching("capital_expenditures", base)
        output.append(
            observation(
                "free_cash_flow",
                base["start"],
                base["end"],
                base["kind"],
                Decimal(base["value"]) - Decimal(capex["value"]) if capex else None,
                base["sources"] + (capex["sources"] if capex else []),
                "difference",
                None if capex else "Matching capital expenditure period unavailable",
            )
        )
    for metric, growth in [
        ("revenue", "revenue_growth"),
        ("operating_cash_flow", "cash_flow_growth"),
    ]:
        for base in series[metric]:
            previous = [
                x
                for x in series[metric]
                if x["kind"] == base["kind"]
                and 350 <= days(x["end"], base["end"]) <= 380
                and abs(days(x["start"], x["end"]) - days(base["start"], base["end"]))
                <= 10
            ]
            prior = (
                min(previous, key=lambda x: abs(days(x["end"], base["end"]) - 366))
                if previous
                else None
            )
            valid = (
                prior is not None
                and compatible(base, prior)
                and Decimal(prior["value"]) > 0
            )
            output.append(
                observation(
                    growth,
                    base["start"],
                    base["end"],
                    base["kind"],
                    (Decimal(base["value"]) / Decimal(prior["value"]) - 1) * 100
                    if valid
                    else None,
                    base["sources"] + (prior["sources"] if prior else []),
                    "year_over_year",
                    None
                    if valid
                    else "Comparable prior-year period with same tags and positive denominator required",
                )
            )
    for metric, names in INSTANT_TAGS.items():
        selected = {}
        for priority, tag in enumerate(names):
            for f in tags.get(tag, {}).get("units", {}).get("USD", []):
                if (
                    f.get("start")
                    or f.get("filed", "9999") > cutoff
                    or f.get("form") not in ("10-K", "10-Q", "10-K/A", "10-Q/A")
                ):
                    continue
                rank = (-priority, f["filed"], f.get("accn", ""))
                if f["end"] not in selected or rank > selected[f["end"]][0]:
                    selected[f["end"]] = (
                        rank,
                        observation(
                            metric,
                            None,
                            f["end"],
                            "instant",
                            Decimal(str(f["val"])),
                            [source(tag, f)],
                            "balance",
                        ),
                    )
        output.extend(o for _, o in selected.values())
    # Debt is an instant balance, never a duration or annual flow.
    debt_tags = [
        "LongTermDebtCurrent",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndFinanceLeaseObligationsIncludingCurrentMaturities",
    ]
    debt = {}
    for tag in debt_tags:
        for f in sorted(
            tags.get(tag, {}).get("units", {}).get("USD", []),
            key=lambda f: (f.get("filed", ""), f.get("accn", "")),
        ):
            if not f.get("start") and f.get("filed", "9999") <= cutoff:
                debt.setdefault(f["end"], {})[tag] = f
    for end, values in debt.items():
        total = values.get(debt_tags[2])
        if total:
            inputs = [(debt_tags[2], total)]
        elif (
            all(t in values for t in debt_tags[:2])
            and values[debt_tags[0]]["filed"] == values[debt_tags[1]]["filed"]
        ):
            inputs = [(t, values[t]) for t in debt_tags[:2]]
        else:
            continue
        output.append(
            observation(
                "debt",
                None,
                end,
                "instant",
                sum((Decimal(str(f["val"])) for _, f in inputs), Decimal(0)),
                [source(t, f) for t, f in inputs],
                "balance",
            )
        )
    return sorted(output, key=lambda o: (o["end"], o["metric"], o["kind"]))
