"""Date, SQL and schema helpers, and the same-day upsert, shared by the health packages.

Owns no table, runs no statement and calls no module, so every health package can use it. The
statement builders return an unexecuted ``select`` for a model the calling package passes in; the
package's ``crud`` executes it. The serializers turn an ORM row into the read schema the caller names.
"""

import calendar
import uuid
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy import ColumnElement, Date, Select, SQLColumnExpression, cast, desc, func, select
from sqlalchemy.orm import Mapped, QueryableAttribute, Session, declared_attr
from sqlalchemy.orm.exc import StaleDataError

import core.date_range as core_date_range
import core.exceptions as core_exceptions
import modules.health.constants as health_constants


class _HasId(Protocol):
    """A stored record, which has an id."""

    id: uuid.UUID


class OwnedRecord(Protocol):
    """The ORM class of a stored record that belongs to a user.

    The columns are declared as SQLAlchemy declares a mixin's, so on the class they are SQL expressions and
    on a row their values.
    """

    @declared_attr
    def id(cls) -> Mapped[uuid.UUID]:
        """The record's primary key."""
        ...

    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        """The record's owner."""
        ...


def to_read_schema[SchemaT: BaseModel](schema: type[SchemaT], row: object) -> SchemaT:
    """Convert an ORM row into its serialized schema.

    Args:
        schema: The read schema to validate the row against.
        row: The ORM row to convert.

    Returns:
        The row as ``schema``.

    Raises:
        ValidationError: If the row does not satisfy the schema.
    """
    return schema.model_validate(row)


def to_read_schemas[SchemaT: BaseModel](schema: type[SchemaT], rows: Sequence[object]) -> list[SchemaT]:
    """Convert ORM rows into their serialized schemas.

    Args:
        schema: The read schema to validate each row against.
        rows: The ORM rows to convert.

    Returns:
        The rows as ``schema``, in the order given.
    """
    return [to_read_schema(schema, row) for row in rows]


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


def interval_start(interval: health_constants.Interval | None, today: Callable[[], date]) -> date | None:
    """Return the first date of an interval, or ``None`` when no interval is given.

    Args:
        interval: The interval to resolve.
        today: Reads the athlete's current calendar date; called only when an interval is given.

    Returns:
        The interval's start date, or ``None`` when no interval is given.
    """
    if interval is None:
        return None
    return get_start_date_for_interval(interval.value, today())


def window_bounds(
    interval: health_constants.Interval | None, date_range: core_date_range.DateRange, today: Callable[[], date]
) -> tuple[date | None, date | None]:
    """Resolve the first and last day a list or chart covers.

    An explicit ``date_range`` replaces ``interval`` altogether: the interval always looks back from today, so
    keeping it would cut a past range down to nothing. Without a range the interval gives the first day and
    the window is open-ended.

    Args:
        interval: The interval looking back from today, if any.
        date_range: The inclusive dates the client gave, if any.
        today: Reads the athlete's current calendar date; called only when it is needed.

    Returns:
        The first and the last day to include; ``None`` for a side with no bound.
    """
    if date_range.is_set:
        return date_range.start_date, date_range.end_date
    return interval_start(interval, today), None


def date_bounds(column: SQLColumnExpression[date], since: date | None, until: date | None) -> list[ColumnElement[bool]]:
    """Build the conditions that keep a date column within a window.

    Args:
        column: The date column or expression to bound.
        since: First day to include, or ``None`` for no lower bound.
        until: Last day to include, or ``None`` for no upper bound.

    Returns:
        The conditions to add to a ``where``; empty for an open window.
    """
    bounds: list[ColumnElement[bool]] = []
    if since is not None:
        bounds.append(column >= since)
    if until is not None:
        bounds.append(column <= until)
    return bounds


def owned_record_statement[ModelT: OwnedRecord](
    model: type[ModelT], record_id: uuid.UUID, user_id: uuid.UUID
) -> Select[tuple[ModelT]]:
    """Build the query for a user's record by id.

    Args:
        model: The record's ORM class.
        record_id: The record to select.
        user_id: The record's owner.

    Returns:
        The unexecuted ``select``.
    """
    return select(model).where(model.id == record_id, model.user_id == user_id)


def owned_record_exists_statement[ModelT: OwnedRecord](
    model: type[ModelT], record_id: uuid.UUID, user_id: uuid.UUID
) -> Select[tuple[bool]]:
    """Build the query that reports whether a user has a record.

    Args:
        model: The record's ORM class.
        record_id: The record to look for.
        user_id: The record's owner.

    Returns:
        The unexecuted ``select`` of one boolean.
    """
    return select(select(model.id).where(model.id == record_id, model.user_id == user_id).exists())


def user_record_count_statement[ModelT: OwnedRecord](
    model: type[ModelT],
    user_id: uuid.UUID,
    since_column: SQLColumnExpression[date],
    since: date | None,
    until: date | None,
    conditions: Sequence[ColumnElement[bool]] = (),
) -> Select[tuple[int]]:
    """Build the query that counts a user's records.

    Args:
        model: The record's ORM class.
        user_id: The records' owner.
        since_column: The column ``since`` and ``until`` are compared against.
        since: Count only records whose ``since_column`` is on or after this date.
        until: Count only records whose ``since_column`` is on or before this date.
        conditions: Further conditions a counted record must meet.

    Returns:
        The unexecuted ``select`` of the count.
    """
    return (
        select(func.count())
        .select_from(model)
        .where(model.user_id == user_id, *date_bounds(since_column, since, until), *conditions)
    )


def user_records_statement[ModelT: OwnedRecord](
    model: type[ModelT],
    user_id: uuid.UUID,
    order_column: QueryableAttribute[date],
    since_column: SQLColumnExpression[date],
    since: date | None,
    until: date | None,
    page_number: int | None,
    num_records: int | None,
    conditions: Sequence[ColumnElement[bool]] = (),
) -> Select[tuple[ModelT]]:
    """Build the query for a user's records, newest first, optionally bounded and paginated.

    Args:
        model: The record's ORM class.
        user_id: The records' owner.
        order_column: The column the records are ordered by, descending.
        since_column: The column ``since`` and ``until`` are compared against.
        since: Select only records whose ``since_column`` is on or after this date.
        until: Select only records whose ``since_column`` is on or before this date.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        conditions: Further conditions a selected record must meet.

    Returns:
        The unexecuted ``select``.
    """
    stmt = select(model).where(model.user_id == user_id, *date_bounds(since_column, since, until), *conditions)
    stmt = stmt.order_by(desc(order_column))
    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)
    return stmt


def local_date_expression(column: SQLColumnExpression[datetime], tz_name: str) -> SQLColumnExpression[date]:
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


def chart_bucket_expression(
    day_column: SQLColumnExpression[date], bucket: health_constants.ChartBucket, since: date
) -> SQLColumnExpression[date]:
    """Return ``day_column`` (a date) truncated to the first day of its chart bucket, within the window.

    The bucket the window opens in is dated the window's first day rather than its own first day, so a
    point is never labelled with a day the chart does not cover.

    Args:
        day_column: A date column or expression.
        bucket: The span to truncate to.
        since: First day of the charted window.

    Returns:
        A SQL expression yielding the bucket's first day inside the window.
    """
    return func.greatest(cast(func.date_trunc(bucket.value, day_column), Date), since)


def chart_points[PointT](
    fetch: Callable[[health_constants.ChartBucket], list[PointT]],
) -> tuple[health_constants.ChartBucket, list[PointT]]:
    """Fetch a chart in the finest bucket that keeps it within ``MAX_CHART_POINTS``.

    Args:
        fetch: Reads the chart's points aggregated in the given bucket.

    Returns:
        The bucket used and its points; the coarsest bucket is used whatever its size.
    """
    for bucket in health_constants.CHART_BUCKETS[:-1]:
        points = fetch(bucket)
        if len(points) <= health_constants.MAX_CHART_POINTS:
            return bucket, points
    bucket = health_constants.CHART_BUCKETS[-1]
    return bucket, fetch(bucket)


def bucket_day_count(start: date, bucket: health_constants.ChartBucket, since: date, today: date) -> int:
    """Count the days of a chart bucket that fall inside the charted window.

    The window opens at ``since`` and closes at ``today``, so the first and the current bucket count only
    the days they actually span.

    Args:
        start: The bucket's first day.
        bucket: The span the bucket aggregates.
        since: First day of the charted window.
        today: The athlete's current calendar date.

    Returns:
        The number of days, at least one.
    """
    if bucket is health_constants.ChartBucket.DAY:
        return 1
    if bucket is health_constants.ChartBucket.WEEK:
        end = start + timedelta(days=6)
    else:
        end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
    return max((min(end, today) - max(start, since)).days + 1, 1)


def upsert_for_day[RecordT: _HasId](
    find: Callable[[], RecordT | None],
    create: Callable[[], RecordT],
    edit: Callable[[uuid.UUID], RecordT],
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
