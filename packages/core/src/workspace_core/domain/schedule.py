"""Task timing. The server owns when work is due; models never infer schedules from prose.

A schedule is a small, explicit value in the task's own timezone:

    {"kind": "manual"}                                   due whenever it is marked ready
    {"kind": "once", "at": "2026-10-01T09:00"}           once, at a local date and time
    {"kind": "daily", "time": "09:00"}
    {"kind": "weekly", "days": ["mon", "thu"], "time": "09:00"}
    {"kind": "monthly", "day": 1, "time": "09:00"}       day 29-31 means the month's last day
                                                         in shorter months

`next_after` returns the first occurrence strictly after a moment, in UTC. Local times keep
their wall-clock meaning across daylight saving changes.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from workspace_core.errors import ValidationFailed

KINDS = ("manual", "once", "daily", "weekly", "monthly")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationFailed(
            f"Unknown timezone {name!r}; use an IANA name such as America/New_York.",
            field="timezone",
        ) from exc


@dataclass(frozen=True)
class Schedule:
    kind: str = "manual"
    at: str | None = None
    time: str | None = None
    days: tuple[str, ...] = ()
    day: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Schedule:
        data = dict(data or {"kind": "manual"})
        kind = str(data.get("kind") or "manual")
        if kind not in KINDS:
            raise ValidationFailed(
                f"Schedule kind must be one of {', '.join(KINDS)}.", field="schedule.kind"
            )
        if kind == "manual":
            return cls()
        if kind == "once":
            at = str(data.get("at") or "")
            try:
                moment = datetime.fromisoformat(at)
            except ValueError as exc:
                raise ValidationFailed(
                    "Schedule 'at' must be a local date and time such as 2026-10-01T09:00.",
                    field="schedule.at",
                ) from exc
            if moment.tzinfo is not None:
                raise ValidationFailed(
                    "Schedule 'at' is a local time in the task's timezone; leave out the offset.",
                    field="schedule.at",
                )
            return cls(kind=kind, at=moment.strftime("%Y-%m-%dT%H:%M"))
        clock = str(data.get("time") or "")
        if not _TIME.match(clock):
            raise ValidationFailed(
                "Schedule 'time' must be HH:MM on a 24-hour clock.", field="schedule.time"
            )
        if kind == "daily":
            return cls(kind=kind, time=clock)
        if kind == "weekly":
            days = [str(d).lower()[:3] for d in data.get("days") or []]
            if not days or any(d not in DAYS for d in days):
                raise ValidationFailed(
                    "A weekly schedule needs one or more days: " + ", ".join(DAYS) + ".",
                    field="schedule.days",
                )
            ordered = tuple(d for d in DAYS if d in set(days))
            return cls(kind=kind, time=clock, days=ordered)
        raw_day = data.get("day")
        day = raw_day if isinstance(raw_day, int) else 0
        if not 1 <= day <= 31:
            raise ValidationFailed(
                "A monthly schedule needs a day between 1 and 31.", field="schedule.day"
            )
        return cls(kind=kind, time=clock, day=day)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.at:
            out["at"] = self.at
        if self.time:
            out["time"] = self.time
        if self.days:
            out["days"] = list(self.days)
        if self.day:
            out["day"] = self.day
        return out

    @property
    def recurring(self) -> bool:
        return self.kind in ("daily", "weekly", "monthly")

    def next_after(self, after: datetime, timezone: str) -> datetime | None:
        """The first occurrence strictly after `after` (aware), in UTC; None if none."""
        tz = zone(timezone)
        if self.kind == "manual":
            return None
        if self.kind == "once":
            assert self.at is not None
            moment = datetime.fromisoformat(self.at).replace(tzinfo=tz).astimezone(UTC)
            return moment if moment > after else None
        assert self.time is not None
        hour, minute = (int(part) for part in self.time.split(":"))
        local_day = after.astimezone(tz).date()
        # Scan forward day by day: at most a few months for any valid schedule.
        for offset in range(0, 400):
            candidate_day = local_day + timedelta(days=offset)
            if not self._matches(candidate_day):
                continue
            moment = datetime.combine(candidate_day, time(hour, minute), tzinfo=tz)
            moment = moment.astimezone(UTC)
            if moment > after:
                return moment
        return None  # pragma: no cover - unreachable for a validated schedule

    def _matches(self, day: date) -> bool:
        if self.kind == "daily":
            return True
        if self.kind == "weekly":
            return DAYS[day.weekday()] in self.days
        assert self.day is not None
        last = calendar.monthrange(day.year, day.month)[1]
        return day.day == min(self.day, last)

    def describe(self, timezone: str) -> str:
        if self.kind == "manual":
            return "Manual: runs when marked ready"
        if self.kind == "once":
            return f"Once on {self.at} ({timezone})"
        if self.kind == "daily":
            return f"Every day at {self.time} ({timezone})"
        if self.kind == "weekly":
            names = [DAY_NAMES[DAYS.index(d)] for d in self.days]
            joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            return f"Every {joined} at {self.time} ({timezone})"
        return f"Monthly on day {self.day} at {self.time} ({timezone})"
