"""Centralized timezone conversion utilities."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

# ISO 8601 datetime format without offset, used for the
# naive UTC wall-clock strings persisted by file parsers.
_DT_FMT = "%Y-%m-%dT%H:%M:%S"


def today_in(tz_name: str) -> date:
    """Return today's calendar date in the given IANA timezone.

    "Which day is it?" is a local question that the server cannot answer from
    its own clock: a request carries no timezone, so ``date.today()`` silently
    answers in the container's zone and ``datetime.now(UTC).date()`` in UTC.
    Either is wrong for any user not on that zone — a day behind for up to 13
    hours at UTC+13, a day ahead for up to 11 hours at UTC-11.

    Callers supply the zone explicitly (typically the athlete's stored
    ``users.timezone``, falling back to ``settings.TZ``) so the choice is
    visible at the call site rather than buried in a default.

    Args:
        tz_name: IANA timezone name to resolve "today" in.

    Returns:
        The current calendar date in that timezone.
    """
    return datetime.now(ZoneInfo(tz_name)).date()


def to_utc_aware(dt: datetime | str | None) -> datetime | None:
    """
    Normalize a datetime or ISO string to UTC-aware.

    Parses ISO 8601 strings and attaches UTC to naive
    datetimes (the import parsers emit naive UTC wall
    clock values). Ensures stored timestamps carry an
    explicit UTC offset instead of relying on the
    database session timezone.

    Args:
        dt: A datetime, ISO 8601 string, or None.

    Returns:
        A UTC-aware datetime, or None if dt is None.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("UTC"))


def format_utc(dt: datetime | str | None) -> str:
    """
    Format a datetime as a UTC ISO 8601 string (no offset).

    File timestamps may carry a non-UTC offset (e.g.
    2026-03-28T08:19:19-07:00). Converting to UTC before
    formatting preserves the actual instant; without it the
    offset is silently dropped and the wall-clock is stored
    as if it were UTC. Naive datetimes are assumed to be UTC.

    Args:
        dt: A datetime, ISO 8601 string, or None.

    Returns:
        UTC ISO 8601 string without an offset, or an empty
        string if dt is None.
    """
    aware = to_utc_aware(dt)
    return aware.strftime(_DT_FMT) if aware else ""
