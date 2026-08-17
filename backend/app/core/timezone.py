"""Centralized timezone conversion utilities."""

from datetime import date, datetime, timedelta
from typing import overload
from zoneinfo import ZoneInfo

import core.config as core_config

# ISO 8601 datetime format without offset, used for the
# naive UTC wall-clock strings persisted by file parsers.
_DT_FMT = "%Y-%m-%dT%H:%M:%S"

#: Widest real-world UTC offset (Pacific/Kiritimati, +14:00).
#:
#: Used wherever the server has to be tolerant of a timezone the request never
#: carries: widening an indexable pre-filter on a raw UTC column so it cannot
#: exclude a row the exact local-time predicate would keep, and bounding "is this
#: plausibly the caller's current year?" checks.
MAX_UTC_OFFSET = timedelta(hours=14)


def or_default(tz_name: str | None) -> str:
    """Return the given IANA timezone, or the server's configured default.

    The fallback is a fact about the *server* (``settings.TZ``), so it belongs
    here rather than in whichever domain module happens to hold a nullable
    timezone column.

    Args:
        tz_name: An IANA timezone name, or None.

    Returns:
        An IANA timezone name.
    """
    return tz_name or core_config.settings.TZ


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


@overload
def to_utc_aware(dt: datetime | str) -> datetime: ...


@overload
def to_utc_aware(dt: None) -> None: ...


def to_utc_aware(dt: datetime | str | None) -> datetime | None:
    """
    Normalize a datetime or ISO string to UTC-aware.

    Parses ISO 8601 strings and attaches UTC to naive
    datetimes (the import parsers emit naive UTC wall
    clock values). Ensures stored timestamps carry an
    explicit UTC offset instead of relying on the
    database session timezone.

    The overloads state the actual contract: ``None`` is
    returned only for a ``None`` input, so callers that
    already hold a value do not have to re-check the
    result for ``None``.

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

    Used for the **waypoint** timestamps inside stream payloads, which are
    stored as JSON strings. For an activity's ``start_time``/``end_time`` use
    :func:`to_utc_second` instead — those are real ``datetime`` columns, and
    round-tripping them through a string only to parse it back loses the type
    for no benefit.

    Args:
        dt: A datetime, ISO 8601 string, or None.

    Returns:
        UTC ISO 8601 string without an offset, or an empty
        string if dt is None.
    """
    aware = to_utc_aware(dt)
    return aware.strftime(_DT_FMT) if aware else ""


@overload
def to_utc_second(dt: datetime | str) -> datetime: ...


@overload
def to_utc_second(dt: None) -> None: ...


def to_utc_second(dt: datetime | str | None) -> datetime | None:
    """
    Normalize to UTC-aware and truncate to whole seconds.

    The resolution every ingestion producer already agreed on: the file parsers
    and the provider adapters all used to format their activity start/end times
    with a second-precision pattern and let the schema validator parse them
    back. That round-trip made the value a ``str`` at the type level even though
    every consumer needs a ``datetime``, so this does the same normalization
    directly.

    Truncation is preserved rather than dropped because the start-time duplicate
    check compares stored instants for equality: devices report whole seconds,
    and letting sub-second noise through would make the same activity re-imported
    from a different source look like a new one.

    Args:
        dt: A datetime, ISO 8601 string, or None.

    Returns:
        A UTC-aware datetime with microseconds zeroed, or None if dt is None.
    """
    aware = to_utc_aware(dt)
    return aware.replace(microsecond=0) if aware is not None else None
