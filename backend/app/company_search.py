from .feed_cache import cached_feed, FeedError
from .sec import SecClient, SecError
from .config import settings
from .db import sec_gate


def search_companies(query):
    def load():
        try:
            data = SecClient(settings.sec_user_agent, gate=sec_gate).fetch_json(
                "/files/company_tickers_exchange.json"
            )
            fields = data["fields"]
            return {"companies": [dict(zip(fields, row)) for row in data["data"]]}
        except (SecError, KeyError, TypeError):
            raise FeedError(
                "Company search is unavailable. Check SEC configuration and retry later."
            ) from None

    data, error = cached_feed("sec-directory", load)
    rows = data.get("companies", [])
    if not rows and error:
        raise FeedError(error)
    needle = query.strip().casefold()
    matches = [
        r
        for r in rows
        if needle in str(r.get("ticker", "")).casefold()
        or needle in str(r.get("name", "")).casefold()
    ]
    matches.sort(
        key=lambda r: (
            str(r.get("ticker", "")).casefold() != needle,
            not str(r.get("ticker", "")).casefold().startswith(needle),
            str(r.get("ticker", "")),
        )
    )
    return [
        {
            "ticker": r["ticker"],
            "name": r["name"],
            "cik": str(r["cik"]).zfill(10),
            "exchange": r.get("exchange", ""),
        }
        for r in matches[:12]
    ]
