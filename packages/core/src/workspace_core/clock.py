"""Time, injectable. Every timestamp the core stores is UTC ISO 8601 text, which sorts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """A clock tests move by hand."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FixedClock needs an aware datetime")
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> datetime:
        self._now = self._now + delta
        return self._now

    def set(self, moment: datetime) -> None:
        self._now = moment


def iso(moment: datetime) -> str:
    """`2026-09-28T09:00:00.000000Z`: fixed width, so text order is time order."""
    if moment.tzinfo is None:
        raise ValueError("naive datetime: attach a timezone first")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_iso(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
