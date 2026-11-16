"""Bounded, shared feed cache; network access occurs outside database transactions."""

from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import SessionLocal
from .models import CalendarCache


class FeedError(Exception):
    pass


def cached_feed(name, loader, hours=24, sessions=SessionLocal):
    current = datetime.now(timezone.utc)
    owner = uuid4().hex
    with sessions.begin() as s:
        cache = s.scalar(
            select(CalendarCache)
            .where(CalendarCache.provider == name)
            .with_for_update()
        )
        if cache is None:
            try:
                with s.begin_nested():
                    cache = CalendarCache(provider=name, payload={})
                    s.add(cache)
                    s.flush()
            except IntegrityError:
                cache = s.scalar(
                    select(CalendarCache)
                    .where(CalendarCache.provider == name)
                    .with_for_update()
                )
        if cache.lease_until and cache.lease_until > current.isoformat():
            return cache.payload, cache.error or (
                None if cache.payload else "Loading source schedule"
            )
        if (
            cache.last_attempt
            and not cache.owner
            and current - datetime.fromisoformat(cache.last_attempt)
            < timedelta(hours=hours)
        ):
            return cache.payload, cache.error
        cache.owner, cache.lease_until = (
            owner,
            (current + timedelta(minutes=3)).isoformat(),
        )
        cache.last_attempt = current.isoformat()
    payload, error = None, None
    try:
        payload = loader()
    except FeedError as exc:
        error = str(exc)
    with sessions.begin() as s:
        cache = s.scalar(
            select(CalendarCache)
            .where(CalendarCache.provider == name)
            .with_for_update()
        )
        if cache.owner == owner:
            if payload is not None:
                cache.payload = payload
            cache.error = error
            cache.owner, cache.lease_until = None, None
        return cache.payload, cache.error
