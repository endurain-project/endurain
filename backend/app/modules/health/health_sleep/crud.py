"""CRUD operations for health sleep records."""

from datetime import date as date_type

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
)


def get_health_sleep_number_by_user_id(user_id: int, db: Session, since: date_type | None = None) -> int:
    """Count a user's sleep records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records on or after this date.

    Returns:
        The number of records.
    """
    return health_record_crud.count(SPEC, user_id, health_sleep_models.HealthSleep.date, since, db)


def get_health_sleep_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    since: date_type | None = None,
) -> list[health_sleep_schema.HealthSleepRead]:
    """Retrieve a user's sleep records, optionally paginated and bounded.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        since: Return only records on or after this date.

    Returns:
        The records ordered by date descending.
    """
    return health_record_crud.list_page(
        SPEC,
        user_id,
        health_sleep_models.HealthSleep.date,
        health_sleep_models.HealthSleep.date,
        since,
        page_number,
        num_records,
        db,
    )


def get_health_sleep_by_id(user_id: int, health_sleep_id: int, db: Session) -> health_sleep_schema.HealthSleepRead:
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
    health_sleep_id: int,
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


def delete_health_sleep(user_id: int, health_sleep_id: int, db: Session, *, if_match: str) -> None:
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
    column, user_id: int, since: date_type, bucket: health_constants.ChartBucket, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Average a sleep column per chart bucket.

    Args:
        column: The sleep column to average.
        user_id: The records' owner.
        since: First day of the charted window.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    model = health_sleep_models.HealthSleep
    day = health_computation.chart_bucket_expression(model.date, bucket, since)
    stmt = (
        select(day, func.avg(column))
        .where(model.user_id == user_id, column.is_not(None), model.date >= since)
        .group_by(day)
        .order_by(day)
    )
    return [health_schema.HealthChartPoint(date=d, value=float(value)) for d, value in db.execute(stmt).all()]


def get_health_sleep_chart(
    user_id: int, since: date_type, bucket: health_constants.ChartBucket, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Average a user's total sleep seconds per chart bucket.

    Args:
        user_id: The records' owner.
        since: First day of the charted window.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    return _average_by_bucket(health_sleep_models.HealthSleep.total_sleep_seconds, user_id, since, bucket, db)


def get_health_sleep_resting_heart_rate_chart(
    user_id: int, since: date_type, bucket: health_constants.ChartBucket, db: Session
) -> list[health_schema.HealthChartPoint]:
    """Average a user's resting heart rate per chart bucket.

    Args:
        user_id: The records' owner.
        since: First day of the charted window.
        bucket: The span each point aggregates.
        db: Database session.

    Returns:
        The buckets that hold a value, oldest first.
    """
    return _average_by_bucket(health_sleep_models.HealthSleep.resting_heart_rate, user_id, since, bucket, db)
