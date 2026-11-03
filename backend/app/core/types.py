"""Annotated types for values a client sends, shared by the request schemas and routes."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from pydantic import AfterValidator, Field, StrictInt

#: The largest value of a PostgreSQL ``integer`` column, which every id column is.
INT32_MAX = 2**31 - 1

#: An id a request body references. Strict, positive and inside the column's range, so a value
#: the database cannot store is a validation failure rather than a 500.
RecordId = Annotated[StrictInt, Field(ge=1, le=INT32_MAX)]

#: The earliest date a record may carry.
_EARLIEST = datetime(1900, 1, 1)


def _not_out_of_range_date(value: date) -> date:
    """Reject a date before 1900 or later than tomorrow in UTC.

    A local date is never more than one day ahead of UTC, so tomorrow in UTC admits every real
    "today" and refuses a typo.

    Args:
        value: The submitted date.

    Returns:
        The date, unchanged.

    Raises:
        ValueError: When the date is outside the range.
    """
    if value < _EARLIEST.date() or value > datetime.now(UTC).date() + timedelta(days=1):
        raise ValueError("Date must be between 1900-01-01 and tomorrow")
    return value


def _not_out_of_range_datetime(value: datetime) -> datetime:
    """Reject a datetime before 1900 or more than a day ahead of now.

    A datetime with an offset is compared in UTC; a naive one is compared as given.

    Args:
        value: The submitted datetime.

    Returns:
        The datetime, unchanged.

    Raises:
        ValueError: When the datetime is outside the range.
    """
    now = datetime.now(UTC)
    if value.tzinfo is None:
        earliest, latest = _EARLIEST, now.replace(tzinfo=None) + timedelta(days=1)
    else:
        earliest, latest = _EARLIEST.replace(tzinfo=UTC), now + timedelta(days=1)
    if value < earliest or value > latest:
        raise ValueError("Date must be between 1900-01-01 and tomorrow")
    return value


#: A calendar date of a record (birthdate, a day's measurement).
RecordDate = Annotated[date, AfterValidator(_not_out_of_range_date)]

#: A point in time of a record.
RecordDateTime = Annotated[datetime, AfterValidator(_not_out_of_range_datetime)]
