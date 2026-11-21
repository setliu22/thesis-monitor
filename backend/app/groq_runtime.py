"""Shared, durable Groq admission and validated request checkpoints.

Never sleep for quotas or hold a database transaction during network I/O.
"""

import hashlib
import json
import math
import re
import socket
import ssl
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
        kind="quota",
    ):
        self.kind = kind
        self.delay = max(1, min(86400, math.ceil(delay)))
        super().__init__(reason)


class InvalidModelResponse(ValueError):
    """Groq replied successfully, but its output failed validation."""


class PermanentFailure(ValueError):
    """A credential/model/input configuration issue requiring an explicit retry."""


def connection_failure_message(error):
    cause = error
    while cause is not None:
        message = str(cause).lower()
        if isinstance(cause, socket.gaierror) or (
            "getaddrinfo" in message or "nodename nor servname" in message
        ):
            return "This process could not resolve Groq’s hostname."
        if (
            isinstance(cause, ssl.SSLCertVerificationError)
            or "certificate_verify_failed" in message
        ):
            return "The app could not verify Groq’s TLS certificate."
        if "operation not permitted" in message or "permission denied" in message:
            return "macOS or the network blocked the connection to Groq."
        if "connection refused" in message:
            return "The connection to Groq was refused."
        if "network is unreachable" in message or "no route to host" in message:
            return "The Mac has no network route to Groq."
        if "ssl" in message or "tls" in message:
            return "The encrypted connection to Groq failed during setup."
        cause = cause.__cause__
    if isinstance(error, httpx.ConnectTimeout):
        return "Opening the connection to Groq timed out."
    return "The app could not open a connection to Groq."


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


def budget_wait(entries, cost, at, limits):
    waits = []
    for window, request_cap, token_cap in (
        (60, limits.rpm, limits.tpm),
        (86400, limits.rpd, limits.tpd),
    ):
        recent = [entry for entry in entries if entry["at"] > at - window]
        tokens = sum(entry["tokens"] for entry in recent)
        requests = len(recent)
        for entry in sorted(recent, key=lambda value: value["at"]):
            if requests < request_cap and tokens + cost <= token_cap:
                break
            requests -= 1
            tokens -= entry["tokens"]
            waits.append(entry["at"] + window - at + 1)
    return max(waits, default=0)


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

    def reserve(self, cost, *, stage=None):
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
            waits.append(budget_wait(entries, cost, at, lim))
            wait = max(waits or [0])
            if wait > 0:
                raise Deferred(wait)
            entries.append({
                "id": ident, "at": at, "tokens": cost, "reserved": cost, "stage": stage,
            })
            data["entries"] = entries
            row.payload = data
        return ident

    def release_unsent(self, ident):
        # A connection failure happens before the request reaches Groq.
        with self.sessions.begin() as s:
            row = locked_row(s, "groq:quota:v1")
            data = dict(row.payload or {})
            data["entries"] = [
                entry for entry in data.get("entries", []) if entry["id"] != ident
            ]
            row.payload = data

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
                        e["seconds"] = max(0, at - e["at"])
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
            if h.get("x-ratelimit-remaining-requests", "").isdigit():
                data["provider_requests_remaining"] = int(h["x-ratelimit-remaining-requests"])
                reset = duration(h.get("x-ratelimit-reset-requests"))
                data["provider_requests_reset"] = at + reset if reset else None
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
        has_rejection_fallback = (
            body.get("response_format", {}).get("json_schema", {}).get("name")
            in {"evidence_decisions", "claim_assessment"}
        )
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
            if float((row.payload or {}).get("json_rejected_until", 0)) > at:
                raise InvalidModelResponse("Groq rejected this batch (json_validate_failed).")
            if self.requests >= self.max_new_requests:
                raise Deferred(
                    1,
                    "Continuing the next analysis batches. Completed batches are saved.",
                    kind="yield",
                )
            row.owner, row.lease_until = owner, str(at + 180)
        try:
            schema_name = body.get("response_format", {}).get("json_schema", {}).get("name")
            stage = (
                "assessment" if schema_name in {"claim_assessment", "cited_assessment"}
                else "evidence" if schema_name == "evidence_decisions" else None
            )
            ident = self.reserve(estimate(body), stage=stage)
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
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                self.release_unsent(ident)
                raise Deferred(
                    60,
                    f"{connection_failure_message(exc)} Completed batches are saved.",
                    kind="groq_provider",
                ) from None
            except httpx.TimeoutException:
                raise Deferred(
                    60,
                    "The request to Groq timed out. Completed batches are saved.",
                    kind="groq_provider",
                ) from None
            except httpx.HTTPError:
                raise Deferred(
                    60,
                    "The app could not connect to Groq. Completed batches are saved.",
                    kind="groq_provider",
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
                    60,
                    f"Groq returned a server error (HTTP {response.status_code}). Completed batches are saved.",
                    kind="groq_provider",
                )
            if response.status_code != 200:
                from .analysis import provider_error

                error = provider_error(response)
                if response.status_code == 400 and "json_validate_failed" in str(error):
                    failed = (payload.get("error") or {}).get("failed_generation")
                    recovered = None
                    if isinstance(failed, str):
                        candidate = {
                            "choices": [{
                                "finish_reason": "stop",
                                "message": {"content": failed.strip()},
                            }]
                        }
                        try:
                            validate(candidate)
                        except ValueError:
                            pass
                        else:
                            recovered = candidate
                    if recovered is None:
                        if has_rejection_fallback:
                            with self.sessions.begin() as s:
                                row = locked_row(s, cache_key)
                                if row.owner == owner:
                                    row.payload = {"json_rejected_until": self.clock() + 3600}
                        raise InvalidModelResponse(str(error))
                    payload = recovered
                elif response.status_code in (400, 401, 403, 404):
                    raise PermanentFailure(str(error))
                else:
                    raise error
            try:
                validate(payload)
            except ValueError as exc:
                if has_rejection_fallback:
                    with self.sessions.begin() as s:
                        row = locked_row(s, cache_key)
                        if row.owner == owner:
                            row.payload = {"json_rejected_until": self.clock() + 3600}
                raise InvalidModelResponse(str(exc)) from exc
            with self.sessions.begin() as s:
                row = locked_row(s, cache_key)
                if row.owner != owner:
                    raise Deferred(
                        5, "Batch lease changed; resuming saved work.", kind="yield"
                    )
                row.payload = {"digest": digest, "response": payload}
            return payload
        finally:
            with self.sessions.begin() as s:
                row = locked_row(s, cache_key)
                if row.owner == owner:
                    row.owner = None
                    row.lease_until = None
