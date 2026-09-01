"""Calendar period calculation utilities."""

from datetime import date, datetime, timedelta
from enum import Enum
from typing import overload

type WeekdayValue = str | Enum

_WEEKDAY_INDICES: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def get_weekday_index(first_day_of_week: WeekdayValue) -> int:
    """
    Return the Python weekday index for a weekday name.

    Args:
        first_day_of_week: Lowercase weekday name or string enum.

    Returns:
        Weekday index where Monday is zero and Sunday is six.

    Raises:
        ValueError: If the weekday name is invalid.
    """
    weekday_name = first_day_of_week.value if isinstance(first_day_of_week, Enum) else first_day_of_week
    if not isinstance(weekday_name, str):
        raise ValueError(f"Invalid first day of week: {weekday_name}")
    try:
        return _WEEKDAY_INDICES[weekday_name]
    except KeyError as err:
        raise ValueError(f"Invalid first day of week: {weekday_name}") from err


@overload
def get_week_start(value: datetime, first_day_of_week: WeekdayValue) -> datetime: ...


@overload
def get_week_start(value: date, first_day_of_week: WeekdayValue) -> date: ...


def get_week_start(value: date, first_day_of_week: WeekdayValue) -> date:
    """
    Return the configured first day on or before a date.

    Args:
        value: Date or datetime within the target week.
        first_day_of_week: Lowercase weekday name or string enum.

    Returns:
        Start of the configured week with the input type preserved.

    Raises:
        ValueError: If the weekday name is invalid.
    """
    first_day_index = get_weekday_index(first_day_of_week)
    days_since_week_start = (value.weekday() - first_day_index) % 7
    return value - timedelta(days=days_since_week_start)
