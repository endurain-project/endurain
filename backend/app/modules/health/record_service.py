"""Application steps the health packages run identically on their per-user records.

The service-layer counterpart of :mod:`modules.health.record_crud`: committing a staged write under the
version-race guard, and charting a metric over an interval. A package passes the :class:`RecordSpec` its
``crud`` describes the record with, and the callables that stage or read what is specific to it.
"""

from collections.abc import Callable
from datetime import date
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.logger as core_logger
import core.pagination as core_pagination
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.record_crud as health_record_crud
import modules.health.schema as health_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


class _DatedRecord(Protocol):
    """A record that is stored once per day."""

    id: int
    date: date | None


def commit_write[ResultT](
    spec: health_record_crud.RecordSpec,
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


def chart(
    user_id: int,
    interval: health_constants.Interval,
    fetch: Callable[[date, health_constants.ChartBucket], list[health_schema.HealthChartPoint]],
    db: Session,
) -> health_schema.HealthChartSeries:
    """Chart a user's metric over an interval in the finest bucket that keeps it readable.

    Args:
        user_id: The records' owner.
        interval: The window to chart.
        fetch: Reads the metric's points from the given first day, aggregated in the given bucket.
        db: Database session.

    Returns:
        The interval's buckets, one point per bucket that holds a value.
    """
    since = health_computation.get_start_date_for_interval(interval.value, users_integration.local_today(user_id, db))
    bucket, points = health_computation.chart_points(lambda bucket: fetch(since, bucket))
    return health_schema.HealthChartSeries(bucket=bucket, points=points)


def list_page[RecordT](
    user_id: int,
    interval: health_constants.Interval | None,
    page_number: int,
    num_records: int,
    count: Callable[[date | None], int],
    fetch: Callable[[date | None], list[RecordT]],
    db: Session,
) -> core_pagination.Page[RecordT]:
    """List one page of a user's records within an interval, with their total.

    Args:
        user_id: The records' owner.
        interval: Return only records within this interval; ``None`` returns them all.
        page_number: 1-based page.
        num_records: Records per page.
        count: Counts the records on or after the given first day (``None`` for no bound).
        fetch: Reads the page's records on or after the given first day (``None`` for no bound).
        db: Database session.

    Returns:
        The page of records; ``total`` counts every record within the interval.
    """
    since = health_computation.interval_start(interval, lambda: users_integration.local_today(user_id, db))
    return core_pagination.Page.build(fetch(since), count(since), page_number, num_records)


def upsert_dated[RecordT: _DatedRecord, CreateT: _DatedRecord, UpdateT: BaseModel](
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
