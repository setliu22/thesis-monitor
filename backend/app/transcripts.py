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


class TranscriptError(FeedError):
    def __init__(self, message, kind="pending"):
        self.kind = kind
        super().__init__(message)


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
        information = (
            str(payload.get("Information") or payload.get("Note") or "")
            if isinstance(payload, dict)
            else ""
        )
        kind = "provider" if information else "malformed"
        if (
            any(
                word in information.lower()
                for word in ("premium", "invalid api key", "invalid apikey")
            )
            and "rate" not in information.lower()
        ):
            kind = "configuration"
        raise TranscriptError(
            "Transcript access is limited or the provider returned the wrong company or fiscal quarter.",
            kind,
        )
    raw = payload.get("transcript")
    if not isinstance(raw, list) or not raw or len(raw) > 2000:
        raise TranscriptError("Transcript has not been published yet.", "pending")
    turns = []
    for i, row in enumerate(raw):
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("content"), str)
            or not isinstance(row.get("speaker"), str)
        ):
            raise TranscriptError(
                "Transcript returned invalid speaker turns.", "malformed"
            )
        content, speaker = clean(row["content"]), clean(row["speaker"])
        if not content or not speaker:
            raise TranscriptError(
                "Transcript returned empty speaker turns.", "malformed"
            )
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
        raise TranscriptError(
            "Transcript access needs ALPHAVANTAGE_API_KEY.", "configuration"
        )
    if not re.fullmatch(r"[A-Z0-9.\-]{1,15}", ticker) or not re.fullmatch(
        r"20\d{2}Q[1-4]", quarter
    ):
        raise TranscriptError(
            "No verified fiscal quarter is available for this filing.", "unavailable"
        )

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
                        kind = (
                            "configuration"
                            if response.status_code in (401, 403)
                            else "provider"
                            if response.status_code == 429
                            or response.status_code >= 500
                            else "unavailable"
                        )
                        raise TranscriptError(
                            "Transcript provider unavailable; filing comparison is still available.",
                            kind,
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
        except TranscriptError as exc:
            raise FeedError(f"transcript-error:{exc.kind}:{exc}") from None
        except httpx.HTTPError:
            raise FeedError(
                "transcript-error:provider:Transcript provider is temporarily unavailable."
            ) from None
        except (ValueError, UnicodeError):
            raise FeedError(
                "transcript-error:malformed:Transcript provider returned an invalid response."
            ) from None

    payload, error = cached_feed(
        f"transcript:{ticker}:{quarter}", load, hours=24, sessions=sessions
    )
    if error:
        if error.startswith("transcript-error:"):
            _, kind, message = error.split(":", 2)
            raise TranscriptError(message, kind)
        raise TranscriptError(error, "pending")
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


def full_transcript_batches(turns):
    """Cover every distinct unit, retaining all occurrences of repeated text."""
    catalog = {}
    for turn in turns:
        text = clean(turn["content"])
        start = 0
        while start < len(text):
            end = min(start + 550, len(text))
            if end < len(text):
                sentence = max(
                    text.rfind(mark, start + 250, end) for mark in (". ", "? ", "! ")
                )
                boundary = text.rfind(" ", start + 250, end)
                if sentence > start:
                    end = sentence + 1
                elif boundary > start:
                    end = boundary
            block = text[start:end]
            origin = {
                "speaker": turn["speaker"],
                "turn": turn.get("turn"),
                "title": turn.get("title", ""),
                "start": start,
                "end": end,
            }
            if block not in catalog:
                catalog[block] = {"text": block, **origin, "occurrences": []}
            catalog[block]["occurrences"].append(origin)
            if len(catalog) > 10000:
                raise FeedError("Transcript has too many passages for bounded review.")
            start = end
            while start < len(text) and text[start].isspace():
                start += 1
    batches = []
    current = []
    size = 0
    for passage in catalog.values():
        cost = len(passage["text"]) + (len(BREAK) if current else 0)
        if current and (size + cost > 7500 or len(current) >= 32):
            batches.append(
                {"passages": current, "text": BREAK.join(p["text"] for p in current)}
            )
            current = []
            size = 0
            cost = len(passage["text"])
        current.append(passage)
        size += cost
    if current:
        batches.append(
            {"passages": current, "text": BREAK.join(p["text"] for p in current)}
        )
    return batches


def compare_transcript(
    payload, thesis, config, transport=None, runner=None, progress=None
):
    from .analysis import analyze_filing, ANALYSIS_PROMPT

    batches = full_transcript_batches(payload["turns"])
    call_prompt = (
        ANALYSIS_PROMPT
        + " This source is an earnings-call transcript. Analyst questions are questions, not company statements or established facts. Generic optimism, budget growth, execution or financial results do not match a valuation claim unless the passage specifically addresses valuation, a multiple or a stock price. Do not match a methodological disclaimer about assessing expectations against future filings to a business passage. Prefer concrete business subjects over a generic company identity."
    )
    observations = []
    considered = classified = rejected = 0
    for index, batch in enumerate(batches):
        if progress:
            progress("transcript", index, len(batches))
        result = analyze_filing(
            batch["text"],
            thesis,
            config,
            transport=transport,
            prompt=call_prompt,
            runner=runner,
            passage_units=[p["text"] for p in batch["passages"]],
        )
        source = {p["text"]: p for p in batch["passages"]}
        for observation in result["observations"]:
            passage = source[observation["quote"]]
            observation.update(
                {k: passage[k] for k in ("speaker", "turn", "title", "occurrences")}
            )
            observations.append(observation)
        considered += result["coverage"]["passages_considered"]
        classified += result["coverage"]["passages_classified"]
        rejected += result["rejected_count"]
    if considered != classified:
        raise ValueError(
            "Incomplete transcript coverage; no completed call comparison saved."
        )
    if progress:
        progress("transcript", len(batches), len(batches))
    return {
        "observations": observations,
        "rejected_count": rejected,
        "selection_method": "complete_passage_classification",
        "coverage": {
            "passages_considered": considered,
            "passages_classified": classified,
            "batches": len(batches),
            "full_transcript": True,
        },
        "status": "included",
        "quarter": payload["quarter"],
        "symbol": payload["symbol"],
        "source_url": payload["source_url"],
        "retrieval": {
            "version": "full-speaker-batches-v2",
            "total_turns": len(payload["turns"]),
            "document_characters": sum(len(t["content"]) for t in payload["turns"]),
            "reviewed_characters": sum(len(b["text"]) for b in batches),
        },
        "supplied_excerpts": BREAK.join(b["text"] for b in batches),
        "scope": "Every distinct transcript text unit classified against the supplied thesis. Repeated text retains all speaker occurrences. Management statements, analyst questions and model relevance judgments are unverified.",
    }
