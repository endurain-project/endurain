"""Tests for calendar period calculation utilities."""

from datetime import UTC, date, datetime
from enum import Enum

import pytest

import core.calendar as core_calendar


class StringWeekday(Enum):
    """String weekday fixture."""

    SUNDAY = "sunday"


@pytest.mark.parametrize(
    ("first_day_of_week", "expected"),
    [
        ("monday", date(2024, 1, 15)),
        ("tuesday", date(2024, 1, 9)),
        ("wednesday", date(2024, 1, 10)),
        ("thursday", date(2024, 1, 11)),
        ("friday", date(2024, 1, 12)),
        ("saturday", date(2024, 1, 13)),
        ("sunday", date(2024, 1, 14)),
    ],
)
def test_get_week_start(first_day_of_week: str, expected: date):
    """Test configurable week starts."""
    assert core_calendar.get_week_start(date(2024, 1, 15), first_day_of_week) == expected


def test_get_week_start_preserves_datetime():
    """Test datetime type, time, and timezone preservation."""
    value = datetime(2024, 1, 15, 12, 30, tzinfo=UTC)

    result = core_calendar.get_week_start(value, "sunday")

    assert result == datetime(2024, 1, 14, 12, 30, tzinfo=UTC)


def test_get_week_start_accepts_string_enum():
    """Test string enum normalization."""
    assert core_calendar.get_week_start(date(2024, 1, 15), StringWeekday.SUNDAY) == date(2024, 1, 14)


def test_get_weekday_index_rejects_invalid_name():
    """Test invalid weekday rejection."""
    with pytest.raises(ValueError, match="Invalid first day of week"):
        core_calendar.get_weekday_index("invalid")
