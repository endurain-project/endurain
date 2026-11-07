"""Application steps the health packages run identically on their per-user records.

The service-layer counterpart of :mod:`modules.health.record_crud`: committing a staged write under the
version-race guard, and charting a metric over an interval. A package passes the :class:`RecordSpec` its
``crud`` describes the record with, and the callables that stage or read what is specific to it.
"""

from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

import core.date_range as core_date_range
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.record_crud as health_record_crud
import modules.health.schema as health_schema
import modules.users.users.integration_service as users_integration
import modules.users.users_profile.contracts as users_profile_contracts

logger = core_logger.get_logger(__name__)


class _DatedRecord(Protocol):
    """A record that is stored once per day."""

    id: int
    date: date | None


class _DatedInput(Protocol):
    """A record to store once per day; without a date it is stored for the user's local today."""

    date: date | None

    def model_dump(self) -> dict[str, object]:
        """Return the record's fields."""
        ...


def require_not_future(user_id: int, when: date | datetime | None, db: Session, *, what: str) -> None:
    """Refuse a manual record dated after the user's local today.

    An instant counts as the day it falls on in the user's own time zone.

    Args:
        user_id: The record's owner.
        when: The date or instant the client sent, or ``None`` when it sent none.
        db: Database session.
        what: The record as the error names it, such as ``"A weight"``.

    Raises:
        InvalidInputError: If the date is after the user's local today.
    """
    if when is None:
        return
    day = (
        when.astimezone(ZoneInfo(users_integration.resolve_timezone(user_id, db))).date()
        if isinstance(when, datetime)
        else when
    )
    if day > users_integration.local_today(user_id, db):
        raise core_exceptions.InvalidInputError(f"{what} cannot be dated in the future")


def commit_write[ModelT: health_record_crud.Row, ReadT: BaseModel, ResultT](
    spec: health_record_crud.RecordSpec[ModelT, ReadT],
    record_id: int,
    user_id: int,
    write: Callable[[], ResultT],
    db: Session,
    *,
    log_message: str,
) -> ResultT:
    """Run a staged write to a user's record, commit it and log the change.

    Args:
        spec: The record type.
        record_id: The record the write changes.
        user_id: The record's owner.
        write: Stages the write.
        db: Database session.
        log_message: What the committed write did, logged at INFO.

    Returns:
        What ``write`` returned.

    Raises:
        NotFoundError: If the user has no such record, or it was deleted before the commit.
        PreconditionFailedError: If the record changed since the client read it.
    """
    with core_etag.refuse_stale_write(
        db, spec.etag_label, lambda: health_record_crud.exists(spec, record_id, user_id, db), spec.not_found
    ):
        result = write()
        db.commit()
    logger.info(log_message, extra=core_logger.context(user_id=user_id, record_id=record_id))
    return result


def get_record[ModelT: health_record_crud.Row, ReadT: BaseModel](
    spec: health_record_crud.RecordSpec[ModelT, ReadT], record_id: int, user_id: int, db: Session
) -> ReadT:
    """Return one of a user's records.

    Args:
        spec: The record type.
        record_id: The record to fetch.
        user_id: The record's owner.
        db: Database session.

    Returns:
        The record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    row = health_record_crud.get_owned(spec, record_id, user_id, db)
    return health_computation.to_read_schema(spec.read_schema, row)


def chart_window(
    user_id: int, interval: health_constants.Interval, date_range: core_date_range.DateRange, db: Session
) -> tuple[date, date | None]:
    """Resolve the first and last day a chart covers.

    Args:
        user_id: The records' owner.
        interval: The window to chart, looking back from today; ignored when ``date_range`` is set.
        date_range: The inclusive dates to chart instead of the interval.
        db: Database session.

    Returns:
        The first day, which is the earliest possible date when only an end was given, and the last day or
        ``None`` for no upper bound.
    """
    since, until = health_computation.window_bounds(
        interval, date_range, lambda: users_integration.local_today(user_id, db)
    )
    return (date.min if since is None else since), until


def chart(
    user_id: int,
    interval: health_constants.Interval,
    date_range: core_date_range.DateRange,
    fetch: Callable[[date, date | None, health_constants.ChartBucket], list[health_schema.HealthChartPoint]],
    db: Session,
) -> health_schema.HealthChartSeries:
    """Chart a user's metric over a window in the finest bucket that keeps it readable.

    Args:
        user_id: The records' owner.
        interval: The window to chart, looking back from today; ignored when ``date_range`` is set.
        date_range: The inclusive dates to chart instead of the interval; a missing start opens at the first
            record.
        fetch: Reads the metric's points from the given first and last day (``None`` for no upper bound),
            aggregated in the given bucket.
        db: Database session.

    Returns:
        The window's buckets, one point per bucket that holds a value.
    """
    since, until = chart_window(user_id, interval, date_range, db)
    bucket, points = health_computation.chart_points(lambda bucket: fetch(since, until, bucket))
    return health_schema.HealthChartSeries(bucket=bucket, points=points)


def list_page[RecordT](
    user_id: int,
    interval: health_constants.Interval | None,
    date_range: core_date_range.DateRange,
    page_number: int,
    num_records: int,
    count: Callable[[date | None, date | None], int],
    fetch: Callable[[date | None, date | None], list[RecordT]],
    db: Session,
) -> core_pagination.Page[RecordT]:
    """List one page of a user's records within a window, with their total.

    Args:
        user_id: The records' owner.
        interval: Return only records within this interval, looking back from today; ``None`` returns them
            all. Ignored when ``date_range`` is set.
        date_range: Return only records within these inclusive dates instead of the interval.
        page_number: 1-based page.
        num_records: Records per page.
        count: Counts the records between the given first and last day (``None`` for no bound).
        fetch: Reads the page's records between the given first and last day (``None`` for no bound).
        db: Database session.

    Returns:
        The page of records; ``total`` counts every record within the window.
    """
    since, until = health_computation.window_bounds(
        interval, date_range, lambda: users_integration.local_today(user_id, db)
    )
    return core_pagination.Page.build(fetch(since, until), count(since, until), page_number, num_records)


def upsert_dated[RecordT: _DatedRecord, CreateT: _DatedInput, UpdateT: BaseModel](
    user_id: int,
    record: CreateT,
    to_update: type[UpdateT],
    find: Callable[[str], RecordT | None],
    create: Callable[[CreateT], RecordT],
    edit: Callable[[int, UpdateT], RecordT],
    db: Session,
) -> RecordT:
    """Stage a day's record, or an update to the record the user already has for that day.

    A record without a date is stored for the user's own local today. A writer that creates the day first,
    on this replica or another, is not an error: the record it created is updated instead.

    Args:
        user_id: The record's owner.
        record: The record to store; a missing date is set to the user's local today.
        to_update: The update schema the record is converted to when the day already has a record.
        find: Reads the user's record for the given ISO date, or ``None``.
        create: Stages a new record.
        edit: Stages an update to the record with the given id, overwriting whatever version it holds.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the day's record cannot be created or found.
    """
    if record.date is None:
        # The request carries no timezone, so the day is the athlete's own.
        record.date = users_integration.local_today(user_id, db)

    day = record.date.isoformat()
    update = to_update(**record.model_dump())
    return health_computation.upsert_for_day(
        find=lambda: find(day),
        create=lambda: create(record),
        edit=lambda record_id: edit(record_id, update),
        db=db,
    )


def in_current_names(row: dict[str, Any], renamed: Mapping[str, str]) -> dict[str, Any]:
    """Return an archived row under today's field names and with the defaults a missing value gets.

    An archive written before the units were put in the field names carries the old names, and one written
    before a record always had a source carries ``source: null``; both are read here, at the import boundary,
    so the schemas know only the current names.

    Args:
        row: The archived row.
        renamed: The old field name to the current one.

    Returns:
        The row with renamed keys and no null ``source``.
    """
    return {renamed.get(key, key): value for key, value in row.items() if key != "source" or value is not None}


def restore_archived_records[CreateT: BaseModel](
    records: list[dict[str, Any]],
    schema: type[CreateT],
    stage: Callable[[int, CreateT, Session], bool | BaseModel],
    user_id: int,
    db: Session,
    *,
    kind: str,
    server_derived: frozenset[str] = frozenset(),
    renamed: Mapping[str, str] | None = None,
) -> int:
    """Stage the records of one kind from a profile archive for a user.

    A row is validated as ``schema`` without the identity the archive carries and without the fields the
    server derives on write; an invalid row is logged and skipped.

    Args:
        records: The archived rows of the kind.
        schema: The schema an archived row is validated as.
        stage: Stages a record for a user; returns ``False`` when it kept a record the user already has.
        user_id: The importing user.
        db: Database session.
        kind: The record kind, for the log.
        server_derived: Archived fields the server derives on write, which are dropped.
        renamed: Field names an older archive used, mapped to the current ones.

    Returns:
        The number of records staged.
    """
    staged = 0
    for row in records:
        fields = {
            key: value
            for key, value in in_current_names(users_profile_contracts.without_row_identity(row), renamed or {}).items()
            if key not in server_derived
        }
        try:
            record = schema.model_validate(fields)
        except ValidationError:
            logger.warning("Skipped an invalid health record", extra=core_logger.context(kind=kind))
            continue
        if stage(user_id, record, db) is not False:
            staged += 1
    logger.debug("Imported health records", extra=core_logger.context(kind=kind, count=staged))
    return staged
