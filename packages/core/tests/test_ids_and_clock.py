from datetime import UTC, datetime, timedelta

import pytest

from workspace_core.clock import FixedClock, SystemClock, iso, parse_iso
from workspace_core.ids import is_id, new_id


def test_ids_are_typed_unique_and_time_ordered():
    clock = FixedClock(datetime(2026, 9, 28, 9, 0, tzinfo=UTC))
    first = new_id("task", clock.now())
    clock.advance(timedelta(milliseconds=5))
    second = new_id("task", clock.now())
    assert first.startswith("task_") and len(first) == len("task_") + 26
    assert first != second
    assert first < second
    assert is_id(first, "task")
    assert not is_id(first, "goal")
    assert not is_id("task_not-a-ulid", "task")


def test_unknown_prefix_is_refused():
    with pytest.raises(ValueError):
        new_id("Task!")


def test_iso_round_trip_is_utc_and_sortable():
    moment = datetime(2026, 3, 8, 7, 30, 15, 123456, tzinfo=UTC)
    text = iso(moment)
    assert text == "2026-03-08T07:30:15.123456Z"
    assert parse_iso(text) == moment
    assert iso(moment) < iso(moment + timedelta(microseconds=1))


def test_naive_datetimes_are_refused():
    with pytest.raises(ValueError):
        iso(datetime(2026, 1, 1))


def test_system_clock_is_aware():
    assert SystemClock().now().tzinfo is not None


def test_ids_made_in_the_same_moment_keep_the_order_they_were_made_in():
    moment = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
    made = [new_id("todo", moment) for _ in range(50)]
    assert made == sorted(made) and len(set(made)) == 50
