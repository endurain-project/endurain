"""Reusable SQL building blocks for querying activities.

The activities table is queried from more than one persistence layer — the
activities CRUD itself, the summary aggregations, and gear-component usage
totals. The rules those queries must agree on (above all: *which local day did
this activity happen on?*) live here as an explicit public surface, instead of
each caller reaching into ``activity/crud.py`` for a helper that reads as
private.

Only SQL expressions and conditions belong here — no sessions opened, no rows
fetched, no ORM instances returned.
"""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import modules.activities.activity.models as activities_models

# Widest real-world UTC offset (Pacific/Kiritimati, +14:00). Used to widen the
# indexable pre-filter on the raw UTC column so it can never exclude a row that
# the exact local-time predicate would keep.
MAX_UTC_OFFSET = timedelta(hours=14)


def escape_like(term: str) -> str:
    """Escape SQL LIKE wildcards in a user-provided term.

    Escapes ``\\``, ``%`` and ``_`` so they are matched literally. Use together
    with ``.like(..., escape="\\\\")`` to keep user input from injecting LIKE
    wildcards into search filters.

    Args:
        term: Raw search term.

    Returns:
        Escaped search term safe for use inside a ``LIKE`` pattern.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def local_start_time_expression(db: Session):
    """``Activity.start_time`` as a naive wall clock in the activity's own timezone.

    "Which day did this activity happen on?" is a *local* question: a 07:00 ride
    in UTC+9 belongs to that local day, not to the previous UTC one. ``start_time``
    is stored as ``timestamptz`` and the session runs in UTC, so comparing or
    truncating it directly (``func.date(...)``, ``extract(...)``) silently answers
    in UTC — which put early-morning activities in eastern timezones and late-night
    ones in western timezones into the wrong day, week, month and year.

    Converting through the activity's stored IANA ``timezone`` first makes date
    filters and summary buckets match what the athlete actually experienced.
    Activities with no stored timezone (indoor imports that carried no GPS) fall
    back to UTC.

    Args:
        db: Database session, used to detect the dialect.

    Returns:
        A SQL expression yielding each activity's local wall clock.
    """
    if db.get_bind().dialect.name == "postgresql":
        # ``timezone(zone, timestamptz) -> timestamp`` is Postgres' AT TIME ZONE.
        return func.timezone(
            func.coalesce(activities_models.Activity.timezone, "UTC"),
            activities_models.Activity.start_time,
        )
    # Production is Postgres-only (see core/database.py); other engines appear
    # only in tests, so fall back to the raw UTC value rather than emitting SQL
    # the engine cannot run.
    return activities_models.Activity.start_time


def local_date_range_conditions(
    db: Session,
    start_date: date | None,
    end_date: date | None,
    *,
    end_exclusive: bool,
) -> list:
    """Restrict rows to a date range evaluated in each activity's *local* timezone.

    Pairs the exact local-time predicate with an indexable pre-filter on the raw
    ``start_time`` column, widened by the maximum real UTC offset so it can never
    exclude a row the exact predicate would keep. Without the pre-filter the
    functional timezone expression would stop the query using the ``start_time``
    index at all.

    Args:
        db: Database session.
        start_date: Inclusive local start of the range, or ``None`` for open-ended.
        end_date: End of the local range, or ``None`` for open-ended.
        end_exclusive: Whether ``end_date`` is excluded from the range.

    Returns:
        The conditions to apply to the statement. Empty when both bounds are
        ``None``.
    """
    local = local_start_time_expression(db)
    conditions: list = []

    if start_date is not None:
        start_dt = datetime.combine(start_date, time.min)
        conditions.append(activities_models.Activity.start_time >= start_dt.replace(tzinfo=UTC) - MAX_UTC_OFFSET)
        conditions.append(local >= start_dt)

    if end_date is not None:
        end_dt = datetime.combine(end_date if end_exclusive else end_date + timedelta(days=1), time.min)
        conditions.append(activities_models.Activity.start_time < end_dt.replace(tzinfo=UTC) + MAX_UTC_OFFSET)
        conditions.append(local < end_dt)

    return conditions
