"""Shared market-data adapter; no company-specific routes or mappings."""

import csv
import io
import logging
from datetime import date
from typing import Protocol
import httpx

SOURCE = "https://www.alphavantage.co/documentation/#earnings-calendar"
# This provider authenticates in the query string. Never emit HTTPX request URLs.
logging.getLogger("httpx").setLevel(logging.WARNING)


class CalendarError(Exception):
    pass


class EarningsCalendar(Protocol):
    def events(self) -> dict[str, list[dict]]: ...


class AlphaVantageCalendar:
    def __init__(self, api_key, client=None):
        self.api_key = api_key
        self.client = client

    def events(self):
        if not self.api_key:
            raise CalendarError("Set ALPHAVANTAGE_API_KEY to enable earnings dates.")
        if self.client is not None:
            return self._fetch(self.client)
        with httpx.Client(timeout=25, follow_redirects=False) as client:
            return self._fetch(client)

    def _fetch(self, client):
        try:
            with client.stream(
                "GET",
                "https://www.alphavantage.co/query",
                params={
                    "function": "EARNINGS_CALENDAR",
                    "horizon": "12month",
                    "apikey": self.api_key,
                },
            ) as response:
                if response.status_code != 200:
                    raise CalendarError(
                        f"Earnings provider returned HTTP {response.status_code}."
                    )
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 10_000_000:
                        raise CalendarError(
                            "Earnings calendar exceeded the response limit."
                        )
            text = data.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames or not {
                "symbol",
                "reportDate",
                "fiscalDateEnding",
            } <= set(reader.fieldnames):
                # JSON error responses include quota/entitlement notices; don't persist raw responses.
                raise CalendarError(
                    "Calendar unavailable. Check the provider key, quota and endpoint access."
                )
            result = {}
            for row in reader:
                symbol = (row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                try:
                    day = date.fromisoformat(row["reportDate"])
                    period = date.fromisoformat(row["fiscalDateEnding"])
                except (ValueError, TypeError):
                    continue
                result.setdefault(symbol, []).append(
                    {
                        "date": day.isoformat(),
                        "fiscal_period": period.isoformat(),
                        "status": "estimated",
                        "provider": "alphavantage",
                        "source": SOURCE,
                    }
                )
            return result
        except (httpx.HTTPError, UnicodeError, csv.Error):
            raise CalendarError(
                "Earnings provider request failed; cached dates are retained."
            ) from None
