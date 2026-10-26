"""Date and SQL helpers, and the same-day upsert, shared by the health packages.

Owns no table, runs no statement and calls no module, so every health package can use it.
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Protocol

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import modules.health.constants as health_constants


class _HasId(Protocol):
    """A stored record, which has an id."""

    id: int


def get_start_date_for_interval(interval: str, today: date) -> date:
    """Calculate the start date based on the specified time interval.

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


def upsert_for_day[RecordT: _HasId](
    find: Callable[[], RecordT | None],
    create: Callable[[], RecordT],
    edit: Callable[[int], RecordT],
    db: Session,
) -> RecordT:
    """Stage a day's record, or an update to the record the day already has.

    A writer that creates the day first, on this replica or another, is not an error: the record it
    created is updated instead. A writer that changes the record between the read and the flush is
    retried against what it left, up to ``UPSERT_ATTEMPTS`` times. Each step runs in a savepoint, so a
    lost race does not poison the caller's transaction.

    Args:
        find: Reads the day's record, or None when it has none.
        create: Stages a new record for the day.
        edit: Stages an update to the record with the given id, overwriting whatever version it holds.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the day's record cannot be created or found.
        StaleDataError: If the record keeps changing under every attempt.
    """
    existing = find()
    if existing is None:
        try:
            with db.begin_nested():
                return create()
        except core_exceptions.ConflictError:
            existing = find()
            if existing is None:
                raise
    for attempt in range(health_constants.UPSERT_ATTEMPTS):
        try:
            with db.begin_nested():
                return edit(existing.id)
        except StaleDataError:
            # Another writer changed the row between this read and the flush: read it again and apply on top.
            existing = find()
            if existing is None or attempt == health_constants.UPSERT_ATTEMPTS - 1:
                raise
    raise AssertionError("unreachable")  # pragma: no cover
