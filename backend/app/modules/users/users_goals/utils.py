"""User goals date-window helpers."""

from datetime import datetime, timedelta

import core.calendar as core_calendar
import core.exceptions as core_exceptions


def get_start_end_date_by_interval(
    interval: str,
    date: str,
    first_day_of_week: core_calendar.WeekdayValue,
) -> tuple[datetime, datetime]:
    """Get start and end datetimes for the interval containing a date.

    Args:
        interval: One of yearly, monthly, weekly, or daily.
        date: Date string in YYYY-MM-DD format.
        first_day_of_week: User's configured first weekday.

    Returns:
        Tuple of (start_date, end_date) datetimes.

    Raises:
        InvalidInputError: If an invalid interval is specified.
    """
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    if interval == "yearly":
        start_date = date_obj.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        # Calculate the last second of December 31st of the same year
        end_date = datetime(date_obj.year, 12, 31, 23, 59, 59)
    elif interval == "weekly":
        start_date = core_calendar.get_week_start(date_obj, first_day_of_week)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)  # Sunday
    elif interval == "monthly":
        start_date = date_obj.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Get the first day of next month
        if date_obj.month == 12:
            next_month = start_date.replace(year=date_obj.year + 1, month=1)
        else:
            next_month = start_date.replace(month=date_obj.month + 1)
        # Subtract one second to get the last second of the current month
        end_date = next_month - timedelta(seconds=1)
    elif interval == "daily":
        start_date = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = date_obj.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        raise core_exceptions.InvalidInputError("Invalid interval specified")

    return start_date, end_date
