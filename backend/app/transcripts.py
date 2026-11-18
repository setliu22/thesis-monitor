"""Fiscal-period matched earnings calls, with speaker-preserving passage selection."""

import math
import re
from collections import Counter
import httpx
from bs4 import BeautifulSoup
from .feed_cache import cached_feed, FeedError
from .retrieval import BREAK, clean, tokens

URL = "https://www.alphavantage.co/query"
SOURCE_URL = "https://www.alphavantage.co/documentation/#earnings-call-transcripts"


def fiscal_quarter(html):
    soup = BeautifulSoup(html, "html.parser")

    def values(name):
        return {
            el.get_text(strip=True)
            for el in soup.find_all(
                attrs={"name": re.compile(r"(?:^|:)" + name + r"$", re.I)}
            )
        }

    years, periods = (
        values("DocumentFiscalYearFocus"),
        values("DocumentFiscalPeriodFocus"),
    )
    if len(years) != 1 or len(periods) != 1:
        return None
    year, period = next(iter(years)), next(iter(periods))
    if not re.fullmatch(r"20\d{2}", year) or period not in ("Q1", "Q2", "Q3", "FY"):
        return None
    return year + ("Q4" if period == "FY" else period)


def parse_transcript(payload, ticker, quarter):
    if (
        not isinstance(payload, dict)
        or payload.get("symbol") != ticker
        or payload.get("quarter") != quarter
    ):
        raise FeedError(
            "Transcript unavailable for this company and fiscal quarter, or provider access is limited."
        )
    raw = payload.get("transcript")
    if not isinstance(raw, list) or not raw or len(raw) > 2000:
        raise FeedError(
            "Transcript has not been published or returned valid speaker turns yet."
        )
    turns = []
    for i, row in enumerate(raw):
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("content"), str)
            or not isinstance(row.get("speaker"), str)
        ):
            raise FeedError("Transcript returned invalid speaker turns.")
        content, speaker = clean(row["content"]), clean(row["speaker"])
        if not content or not speaker:
            raise FeedError("Transcript returned empty speaker turns.")
        turns.append(
            {
                "turn": i + 1,
                "speaker": speaker,
                "title": str(row.get("title") or ""),
                "content": content,
            }
        )
    return turns


def fetch_transcript(ticker, quarter, key, sessions, transport=None):
    if not key:
        raise FeedError("Transcript access needs ALPHAVANTAGE_API_KEY.")
    if not re.fullmatch(r"[A-Z0-9.\-]{1,15}", ticker) or not re.fullmatch(
        r"20\d{2}Q[1-4]", quarter
    ):
        raise FeedError("No verified fiscal quarter is available for this filing.")

    def load():
        try:
            with httpx.Client(
                timeout=30, transport=transport, follow_redirects=False
            ) as client:
                with client.stream(
                    "GET",
                    URL,
                    params={
                        "function": "EARNINGS_CALL_TRANSCRIPT",
                        "symbol": ticker,
                        "quarter": quarter,
                        "apikey": key,
                    },
                ) as response:
                    if response.status_code != 200:
                        raise FeedError(
                            "Transcript provider unavailable; filing comparison is still available."
                        )
                    body = bytearray()
                    for part in response.iter_bytes():
                        body.extend(part)
                        if len(body) > 4_000_000:
                            raise FeedError(
                                "Transcript exceeds the supported size limit."
                            )
            import json

            payload = json.loads(body)
            turns = parse_transcript(payload, ticker, quarter)
            return {
                "symbol": ticker,
                "quarter": quarter,
                "turns": turns,
                "source_url": SOURCE_URL,
            }
        except (httpx.HTTPError, ValueError, UnicodeError):
            raise FeedError(
                "Transcript provider unavailable; filing comparison is still available."
            ) from None

    payload, error = cached_feed(
        f"transcript:{ticker}:{quarter}", load, hours=24, sessions=sessions
    )
    if error:
        raise FeedError(error)
    if not payload.get("turns"):
        raise FeedError("Transcript is loading; compare again shortly.")
    return payload


def select_transcript_evidence(turns, thesis):
    # Split within turns so neither retrieval nor quote attribution crosses speakers.
    from .analysis import text_units

    candidates = []
    seen = set()
    for turn in turns:
        for unit in text_units(turn["content"], "P"):
            if unit["text"] not in seen:
                candidates.append(
                    {
                        "text": unit["text"],
                        "speaker": turn["speaker"],
                        "turn": turn.get("turn"),
                        "title": turn.get("title", ""),
                    }
                )
                seen.add(unit["text"])
                if len(candidates) > 10000:
                    raise FeedError(
                        "Transcript has too many passages for bounded review."
                    )
    vocab = [tokens(c["text"]) for c in candidates]
    frequency = Counter(t for v in vocab for t in v)
    query = tokens(thesis)
    weights = {
        t: 1 + math.log((len(candidates) + 1) / (frequency[t] + 1)) for t in query
    }
    claims = [tokens(x) for x in re.split(r"(?<=[.!?])\s+|\n+", thesis) if tokens(x)]
    remaining = set(range(len(candidates)))
    selected = []
    used = 0
    for target_index, target in enumerate(claims + [query] * len(candidates)):
        if (
            not remaining
            or min(
                len(candidates[i]["text"]) + (len(BREAK) if selected else 0)
                for i in remaining
            )
            > 8000 - used
        ):
            break
        added = False
        ranked = sorted(
            remaining,
            key=lambda i: (
                sum(weights.get(t, 0) for t in target & vocab[i])
                / math.sqrt(1 + len(candidates[i]["text"]) / 500),
                -i,
            ),
            reverse=True,
        )
        for i in ranked:
            if not target & vocab[i]:
                break
            cost = len(candidates[i]["text"]) + (len(BREAK) if selected else 0)
            if used + cost <= 8000:
                selected.append(candidates[i])
                remaining.remove(i)
                used += cost
                added = True
                break
        if not added and target_index >= len(claims):
            break
    return {
        "text": BREAK.join(p["text"] for p in selected),
        "passages": selected,
        "total_turns": len(turns),
        "document_characters": sum(len(t["content"]) for t in turns),
        "selected_characters": used,
        "version": "speaker-thesis-lexical-v1",
    }


def compare_transcript(payload, thesis, config, transport=None):
    from .analysis import analyze_filing, ANALYSIS_PROMPT

    retrieval = select_transcript_evidence(payload["turns"], thesis[:4000])
    call_prompt = (
        ANALYSIS_PROMPT
        + " This source is an earnings-call transcript. Analyst questions are questions, not company statements or established facts. Generic optimism, budget growth, execution or financial results do not match a valuation claim unless the passage specifically addresses valuation, a multiple or a stock price. Do not match a methodological disclaimer about assessing expectations against future filings to a business passage. Prefer concrete business subjects over a generic company identity."
    )
    result = analyze_filing(
        retrieval["text"], thesis, config, transport=transport, prompt=call_prompt
    )
    for observation in result["observations"]:
        passage = next(
            p for p in retrieval["passages"] if observation["quote"] == p["text"]
        )
        observation.update({k: passage[k] for k in ("speaker", "turn", "title")})
    return result | {
        "status": "included",
        "quarter": payload["quarter"],
        "symbol": payload["symbol"],
        "source_url": payload["source_url"],
        "retrieval": {k: v for k, v in retrieval.items() if k != "text"},
        "supplied_excerpts": retrieval["text"],
        "scope": "Selected speaker-attributed call passages matched to thesis claims; not a full-call semantic review. Management statements and analyst questions are not verified facts.",
    }
