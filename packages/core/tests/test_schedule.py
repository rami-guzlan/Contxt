from datetime import UTC, datetime

import pytest

from workspace_core.domain.schedule import Schedule
from workspace_core.errors import ValidationFailed

NY = "America/New_York"


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def test_manual_tasks_have_no_clock():
    schedule = Schedule.from_dict({"kind": "manual"})
    assert schedule.next_after(utc(2026, 9, 28, 12), NY) is None
    assert not schedule.recurring
    assert schedule.describe(NY) == "Manual: runs when marked ready"


def test_once_is_local_time_and_happens_once():
    schedule = Schedule.from_dict({"kind": "once", "at": "2026-10-01T09:00"})
    assert schedule.next_after(utc(2026, 9, 28), NY) == utc(2026, 10, 1, 13)
    assert schedule.next_after(utc(2026, 10, 1, 13), NY) is None
    assert not schedule.recurring


def test_daily_is_strictly_after():
    schedule = Schedule.from_dict({"kind": "daily", "time": "09:00"})
    assert schedule.next_after(utc(2026, 9, 28, 12), NY) == utc(2026, 9, 28, 13)
    assert schedule.next_after(utc(2026, 9, 28, 13), NY) == utc(2026, 9, 29, 13)
    assert schedule.recurring


def test_daily_keeps_local_time_across_daylight_saving():
    schedule = Schedule.from_dict({"kind": "daily", "time": "09:00"})
    # US daylight saving time ends on Sunday 1 November 2026.
    assert schedule.next_after(utc(2026, 10, 31, 13), NY) == utc(2026, 11, 1, 14)


def test_weekly_on_chosen_days():
    schedule = Schedule.from_dict({"kind": "weekly", "days": ["thu", "mon"], "time": "08:30"})
    # Sunday 27 September 2026 -> Monday 28 September, 08:30 EDT.
    assert schedule.next_after(utc(2026, 9, 27, 18), NY) == utc(2026, 9, 28, 12, 30)
    assert schedule.next_after(utc(2026, 9, 28, 12, 30), NY) == utc(2026, 10, 1, 12, 30)
    assert schedule.to_dict()["days"] == ["mon", "thu"]
    assert schedule.describe(NY) == "Every Monday and Thursday at 08:30 (America/New_York)"


def test_monthly_clamps_to_short_months():
    schedule = Schedule.from_dict({"kind": "monthly", "day": 31, "time": "07:00"})
    assert schedule.next_after(utc(2026, 9, 1), "UTC") == utc(2026, 9, 30, 7)
    assert schedule.next_after(utc(2026, 9, 30, 7), "UTC") == utc(2026, 10, 31, 7)
    assert schedule.next_after(utc(2027, 2, 1), "UTC") == utc(2027, 2, 28, 7)


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        ({"kind": "hourly"}, "kind"),
        ({"kind": "daily", "time": "25:00"}, "time"),
        ({"kind": "weekly", "days": ["someday"], "time": "09:00"}, "day"),
        ({"kind": "weekly", "days": [], "time": "09:00"}, "day"),
        ({"kind": "monthly", "day": 0, "time": "09:00"}, "day"),
        ({"kind": "once", "at": "next tuesday"}, "at"),
        ({"kind": "once", "at": "2026-10-01T09:00+02:00"}, "local"),
    ],
)
def test_invalid_schedules_say_what_is_wrong(data, fragment):
    with pytest.raises(ValidationFailed) as info:
        Schedule.from_dict(data)
    assert fragment in str(info.value)


def test_unknown_timezone_is_refused():
    with pytest.raises(ValidationFailed):
        Schedule.from_dict({"kind": "daily", "time": "09:00"}).next_after(
            utc(2026, 9, 28), "Mars/Olympus_Mons"
        )


def test_round_trip():
    data = {"kind": "weekly", "days": ["mon"], "time": "09:00"}
    assert Schedule.from_dict(Schedule.from_dict(data).to_dict()) == Schedule.from_dict(data)
    assert Schedule.from_dict(None).kind == "manual"
