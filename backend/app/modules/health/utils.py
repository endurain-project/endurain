"""Utility functions for health-related operations."""

from datetime import date, timedelta

from sqlalchemy import func


def get_start_date_for_interval(interval: str, today: date) -> date:
    """
    Calculate the start date based on the specified time interval.

    Args:
        interval (str): The time interval for which to calculate the start date.
            Supported values:
            - "last_30_days": Returns date from 30 days ago
            - "last_90_days": Returns date from 90 days ago
            - "last_year": Returns date from 365 days ago
            - "all_time": Returns the minimum date (earliest possible date)
            - Any other value defaults to 7 days ago
        today (date): The athlete's current calendar date, resolved from their
            own timezone. Passed in rather than read from the server clock:
            ``date.today()`` answers in the container's zone, which puts a user
            in UTC+13 a day behind for 13 hours out of every 24 and silently
            shifts every interval window by a day.

    Returns:
        date: The calculated start date for the given interval.
    """
    if interval == "last_30_days":
        return today - timedelta(days=30)
    elif interval == "last_90_days":
        return today - timedelta(days=90)
    elif interval == "last_year":
        return today - timedelta(days=365)
    elif interval == "all_time":
        return date.min
    else:
        return today - timedelta(days=7)


def local_date_expression(column, tz_name: str):
    """Return ``column`` (a ``timestamptz``) truncated to a calendar date in ``tz_name``.

    ``func.date()`` on a ``timestamptz`` truncates in the *session* timezone,
    which is pinned to UTC — so a 22:00 local entry in UTC+9 is filed under the
    previous day, and a 20:00 local entry in UTC-5 under the next. Converting
    through the athlete's own zone first makes the day match the one they
    experienced.

    Args:
        column: A timezone-aware datetime column.
        tz_name: IANA timezone to resolve the calendar date in.

    Returns:
        A SQL expression yielding the local calendar date.
    """
    # ``timezone(zone, timestamptz) -> timestamp`` is Postgres' AT TIME ZONE.
    return func.date(func.timezone(tz_name, column))
