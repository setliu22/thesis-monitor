"""Shared, durable Groq admission and validated request checkpoints.

Never sleep for quotas or hold a database transaction during network I/O.
"""

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from uuid import uuid4
import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .models import CalendarCache


class Deferred(Exception):
    def __init__(
        self,
        delay=60,
        reason="Waiting for Groq free-tier allowance. Completed batches are saved.",
    ):
        self.delay = max(1, min(86400, math.ceil(delay)))
        super().__init__(reason)


@dataclass
class Limits:
    tpm: int = 7800
    tpd: int = 180000
    rpm: int = 25
    rpd: int = 900


def locked_row(session, key):
    row = session.scalar(
        select(CalendarCache).where(CalendarCache.provider == key).with_for_update()
    )
    if row is None:
        try:
            with session.begin_nested():
                row = CalendarCache(provider=key, payload={})
                session.add(row)
                session.flush()
        except IntegrityError:
            row = session.scalar(
                select(CalendarCache)
                .where(CalendarCache.provider == key)
                .with_for_update()
            )
    return row


def duration(value):
    if not value:
        return 0
    try:
        return max(0, float(value))
    except ValueError:
        parts = re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h|d)", value)
        return sum(
            float(n) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
            for n, unit in parts
        )


def estimate(body):
    return math.ceil(len(json.dumps(body, ensure_ascii=False)) / 3.5) + int(
        body.get("max_completion_tokens", 1536)
    )


class GroqRunner:
    def __init__(
        self,
        sessions,
        key,
        transport=None,
        limits=None,
        clock=time.time,
        max_new_requests=2,
    ):
        self.sessions, self.key, self.transport = sessions, key, transport
        self.limits, self.clock = limits or Limits(), clock
        self.max_new_requests = max_new_requests
        self.requests = self.cache_hits = self.tokens = 0

    def reserve(self, cost):
        at, ident = self.clock(), uuid4().hex
        lim = self.limits
        if cost > lim.tpm or cost > lim.tpd:
            raise ValueError(
                "Analysis batch exceeds the configured token allowance; use a smaller batch or shorter thesis."
            )
        with self.sessions.begin() as s:
            row = locked_row(s, "groq:quota:v1")
            data = dict(row.payload or {})
            entries = [e for e in data.get("entries", []) if e["at"] > at - 86400]
            waits = [data.get("blocked_until", 0) - at]
            if (
                data.get("provider_reset", 0) > at
                and data.get("provider_remaining", lim.tpm) < cost
            ):
                waits.append(data["provider_reset"] - at)
            minute = [e for e in entries if e["at"] > at - 60]
            for items, cap, window, tokens in [
                (minute, lim.rpm, 60, False),
                (minute, lim.tpm, 60, True),
                (entries, lim.rpd, 86400, False),
                (entries, lim.tpd, 86400, True),
            ]:
                used = sum(e["tokens"] if tokens else 1 for e in items)
                needed = cost if tokens else 1
                if used + needed > cap:
                    for e in sorted(items, key=lambda x: x["at"]):
                        used -= e["tokens"] if tokens else 1
                        if used + needed <= cap:
                            waits.append(e["at"] + window - at + 1)
                            break
            wait = max(waits or [0])
            if wait > 0:
                raise Deferred(wait)
            entries.append({"id": ident, "at": at, "tokens": cost})
            data["entries"] = entries
            row.payload = data
        return ident

    def observe(self, ident, payload, response):
        at = self.clock()
        with self.sessions.begin() as s:
            row = locked_row(s, "groq:quota:v1")
            data = dict(row.payload or {})
            entries = [dict(e) for e in data.get("entries", [])]
            usage = (
                payload.get("usage", {}).get("total_tokens")
                if isinstance(payload, dict)
                else None
            )
            if isinstance(usage, int) and usage >= 0:
                details = payload.get("usage", {}).get("prompt_tokens_details") or {}
                cached = details.get("cached_tokens", 0)
                cached = (
                    cached if isinstance(cached, int) and 0 <= cached <= usage else 0
                )
                quota_tokens = usage - cached
                for e in entries:
                    if e["id"] == ident:
                        e["tokens"] = quota_tokens
                        e["total_tokens"] = usage
                self.tokens += quota_tokens
            data["entries"] = entries
            h = response.headers
            if h.get("x-ratelimit-remaining-tokens", "").isdigit():
                data["provider_remaining"] = int(h["x-ratelimit-remaining-tokens"])
                data["provider_reset"] = at + duration(
                    h.get("x-ratelimit-reset-tokens")
                )
            if response.status_code == 429:
                delay = max(
                    2,
                    duration(h.get("retry-after"))
                    or duration(h.get("x-ratelimit-reset-tokens"))
                    or 60,
                )
                data["blocked_until"] = max(data.get("blocked_until", 0), at + delay)
            if h.get("x-ratelimit-remaining-requests") == "0":
                data["blocked_until"] = max(
                    data.get("blocked_until", 0),
                    at + (duration(h.get("x-ratelimit-reset-requests")) or 86400),
                )
            row.payload = data
        return max(1, data.get("blocked_until", at) - at)

    def __call__(self, body, validate):
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        cache_key = "gb:" + digest[:40]
        owner = uuid4().hex
        at = self.clock()
        with self.sessions.begin() as s:
            row = locked_row(s, cache_key)
            if (row.payload or {}).get(
                "digest"
            ) == digest and "response" in row.payload:
                result = row.payload["response"]
                validate(result)
                self.cache_hits += 1
                return result
            if row.lease_until and float(row.lease_until) > at:
                raise Deferred(
                    5,
                    "Another worker is reviewing this batch. Completed batches are saved.",
                )
            if self.requests >= self.max_new_requests:
                raise Deferred(
                    1,
                    "Continuing the next analysis batches. Completed batches are saved.",
                )
            row.owner, row.lease_until = owner, str(at + 180)
        try:
            ident = self.reserve(estimate(body))
            self.requests += 1
            try:
                with httpx.Client(
                    transport=self.transport, timeout=60, follow_redirects=False
                ) as client:
                    response = client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": "Bearer " + self.key},
                        json=body,
                    )
            except httpx.HTTPError:
                raise Deferred(
                    60, "Groq is temporarily unavailable. Completed batches are saved."
                ) from None
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            delay = self.observe(ident, payload, response)
            if response.status_code == 429:
                raise Deferred(delay)
            if response.status_code >= 500:
                raise Deferred(
                    60, "Groq is temporarily unavailable. Completed batches are saved."
                )
            if response.status_code != 200:
                from .analysis import provider_error

                raise provider_error(response)
            validate(payload)
            with self.sessions.begin() as s:
                row = locked_row(s, cache_key)
                if row.owner != owner:
                    raise Deferred(5, "Batch lease changed; resuming saved work.")
                row.payload = {"digest": digest, "response": payload}
            return payload
        finally:
            with self.sessions.begin() as s:
                row = locked_row(s, cache_key)
                if row.owner == owner:
                    row.owner = None
                    row.lease_until = None
