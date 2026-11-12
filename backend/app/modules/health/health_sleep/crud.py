"""CRUD operations for health sleep records."""

import uuid
from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import ColumnElement, SQLColumnExpression, func, select
from sqlalchemy.orm import Session

import core.sync as core_sync
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_sleep.models as health_sleep_models
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.record_crud as health_record_crud
import modules.health.schema as health_schema

SPEC = health_record_crud.RecordSpec(
    model=health_sleep_models.HealthSleep,
    read_schema=health_sleep_schema.HealthSleepRead,
    not_found="Health sleep not found",
    etag_label="sleep record",
    sync_type="health_sleep",
)

LIST_SPEC = health_record_crud.RecordSpec(
    model=health_sleep_models.HealthSleep,
    read_schema=health_sleep_schema.HealthSleepListItem,
    not_found="Health sleep not found",
    etag_label="sleep record",
    sync_type="health_sleep",
)


def _resting_heart_rate_conditions(has_resting_heart_rate: bool | None) -> list[ColumnElement[bool]]:
    """Build the condition that keeps nights with, or without, a resting heart rate.

    Args:
        has_resting_heart_rate: ``True`` keeps nights that record one, ``False`` nights that do not, ``None``
            every night.

    Returns:
        The condition, or none.
    """
    if has_resting_heart_rate is None:
        return []
    column = health_sleep_models.HealthSleep.resting_heart_rate
    return [column.is_not(None) if has_resting_heart_rate else column.is_(None)]


def get_health_sleep_number_by_user_id(
    user_id: int,
    db: Session,
    since: date_type | None = None,
    until: date_type | None = None,
    *,
    has_resting_heart_rate: bool | None = None,
) -> int:
    """Count a user's sleep records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records on or after this date.
        until: Count only records on or before this date.
        has_resting_heart_rate: Count only nights with (``True``) or without (``False``) a resting heart rate.

    Returns:
        The number of records.
    """
    return health_record_crud.count(
        SPEC,
        user_id,
        health_sleep_models.HealthSleep.date,
        since,
        until,
        db,
        _resting_heart_rate_conditions(has_resting_heart_rate),
    )


def _list_page[ModelT: health_record_crud.Row, ReadT: BaseModel](
    spec: health_record_crud.RecordSpec[ModelT, ReadT],
    user_id: int,
    page_number: int | None,
    num_records: int | None,
    since: date_type | None,
    until: date_type | None,
    db: Session,
    *,
    has_resting_heart_rate: bool | None,
) -> list[ReadT]:
    """Retrieve a user's sleep records as a spec's read schema.

    Args:
        spec: The record type and the schema each row is returned as.
        user_id: The records' owner.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        since: Return only records on or after this date.
        until: Return only records on or before this date.
        db: Database session.
        has_resting_heart_rate: Return only nights with (``True``) or without (``False``) a resting heart rate.

    Returns:
        The records ordered by date descending.
    """
    return health_record_crud.list_page(
        spec,
        user_id,
        health_sleep_models.HealthSleep.date,
        health_sleep_models.HealthSleep.date,
        since,
        until,
        page_number,
        num_records,
        db,
        _resting_heart_rate_conditions(has_resting_heart_rate),
    )


def get_health_sleep_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    since: date_type | None = None,
    until: date_type | None = None,
    *,
    has_resting_heart_rate: bool | None = None,
) -> list[health_sleep_schema.HealthSleepRead]:
    """Retrieve a user's sleep records with their stages, optionally paginated and bounded.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        since: Return only records on or after this date.
        until: Return only records on or before this date.
        has_resting_heart_rate: Return only nights with (``True``) or without (``False``) a resting heart rate.

    Returns:
        The records ordered by date descending.
    """
    return _list_page(
        SPEC, user_id, page_number, num_records, since, until, db, has_resting_heart_rate=has_resting_heart_rate
    )


def get_health_sleep_list_items_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    since: date_type | None = None,
    until: date_type | None = None,
    *,
    has_resting_heart_rate: bool | None = None,
) -> list[health_sleep_schema.HealthSleepListItem]:
    """Retrieve a user's sleep records without their stages, optionally paginated and bounded.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        since: Return only records on or after this date.
        until: Return only records on or before this date.
        has_resting_heart_rate: Return only nights with (``True``) or without (``False``) a resting heart rate.

    Returns:
        The records ordered by date descending, each with whether it has stages.
    """
    return _list_page(
        LIST_SPEC, user_id, page_number, num_records, since, until, db, has_resting_heart_rate=has_resting_heart_rate
    )


def get_health_sleep_by_id(
    user_id: int, health_sleep_id: uuid.UUID, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Retrieve a user's sleep record by id.

    Args:
        user_id: The record's owner.
        health_sleep_id: The record to fetch.
        db: Database session.

    Returns:
        The record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    row = health_record_crud.get_owned(SPEC, health_sleep_id, user_id, db)
    return health_computation.to_read_schema(SPEC.read_schema, row)


def get_health_sleep_by_date_and_user_id(
    user_id: int, date: str, db: Session
) -> health_sleep_schema.HealthSleepRead | None:
    """Retrieve a user's sleep record for a date.

    Args:
        user_id: The record's owner.
        date: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    return health_record_crud.find_by_date(SPEC, user_id, date, db)


def create_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepCreate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Stage a new sleep record for a user.

    Args:
        user_id: The record's owner.
        health_sleep: The record to create.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    return health_record_crud.create(
        SPEC, user_id, health_sleep, db, conflict=health_record_crud.duplicate_date_message(health_sleep.date)
    )


def edit_health_sleep(
    user_id: int,
    health_sleep_id: uuid.UUID,
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_sleep_schema.HealthSleepRead:
    """Stage an update to a user's sleep record.

    Args:
        user_id: The record's owner.
        health_sleep_id: The record to change.
        health_sleep: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
        ConflictError: If the new date already has a record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    return health_record_crud.edit(
        SPEC,
        health_sleep_id,
        user_id,
        health_sleep,
        db,
        if_match=if_match,
        conflict=health_record_crud.DATE_TAKEN_MESSAGE,
    )


def delete_health_sleep(user_id: int, health_sleep_id: uuid.UUID, db: Session, *, if_match: str) -> None:
    """Stage the deletion of a user's sleep record.

    Args:
        user_id: The record's owner.
        health_sleep_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    health_record_crud.delete(SPEC, health_sleep_id, user_id, db, if_match=if_match)


def _average_by_bucket(
    column: SQLColumnExpression[int | None],
    user_id: int,
    since: date_type,
    until: date_type | None,
    bucket: health_constants.ChartBucket,
    db: Session,
) -> list[health_schema.HealthChartPoint]:
    """Average a sleep column per chart bucket.

    Args:
        column: The sleep column to average.
        user_id: The records' owner.
        since: First day of the charted window.
        until: Last day of the charted window, or ``None`` for no upper bound.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    model = health_sleep_models.HealthSleep
    day = health_computation.chart_bucket_expression(model.date, bucket, since)
    stmt = (
        select(day, func.avg(column))
        .where(model.user_id == user_id, column.is_not(None), *health_computation.date_bounds(model.date, since, until))
        .group_by(day)
        .order_by(day)
    )
    return [health_schema.HealthChartPoint(date=d, value=float(value)) for d, value in db.execute(stmt).all()]


def get_health_sleep_chart(
    user_id: int, since: date_type, until: date_type | None, bucket: health_constants.ChartBucket, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Average a user's total sleep seconds per chart bucket.

    Args:
        user_id: The records' owner.
        since: First day of the charted window.
        until: Last day of the charted window, or ``None`` for no upper bound.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    return _average_by_bucket(health_sleep_models.HealthSleep.total_sleep_seconds, user_id, since, until, bucket, db)


def get_health_sleep_resting_heart_rate_chart(
    user_id: int, since: date_type, until: date_type | None, bucket: health_constants.ChartBucket, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Average a user's resting heart rate per chart bucket.

    Args:
        user_id: The records' owner.
        since: First day of the charted window.
        until: Last day of the charted window, or ``None`` for no upper bound.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    return _average_by_bucket(health_sleep_models.HealthSleep.resting_heart_rate, user_id, since, until, bucket, db)


def list_changed(
    user_id: int, after: core_sync.Position[uuid.UUID] | None, until: datetime, limit: int, db: Session
) -> list[health_sleep_schema.HealthSleepRead]:
    """Retrieve a user's records changed after a position, oldest change first.

    Args:
        user_id: The records' owner.
        after: Return records strictly after this ``(updated_at, id)``; ``None`` from the first.
        until: Return only records changed before this instant.
        limit: The most records to return.
        db: Database session.

    Returns:
        The records, in ``(updated_at, id)`` order.
    """
    model = health_sleep_models.HealthSleep
    return health_record_crud.list_changed(
        model, model.user_id, model.id, SPEC.read_schema, user_id, after, until, limit, db
    )
