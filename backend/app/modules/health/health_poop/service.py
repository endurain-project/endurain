"""Application logic for health poop (bowel movement) records.

Owns the ownership check, the timezone and interval resolution and the
transaction boundary. What other modules may consume lives in
:mod:`modules.health.health_poop.integration_service`.
"""

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.schema as health_poop_schema
import modules.health.record_service as health_record_service
import modules.health.schema as health_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def list_health_poop(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    interval: health_constants.Interval | None = None,
) -> core_pagination.Page[health_poop_schema.HealthPoopRead]:
    """List one page of a user's poop records with their total.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page.
        num_records: Records per page.
        interval: Return only records within this interval.

    Returns:
        The page of records; ``total`` counts every record within the interval.
    """
    since = health_computation.interval_start(interval, lambda: users_integration.local_today(user_id, db))
    tz_name = users_integration.resolve_timezone(user_id, db)
    total = health_poop_crud.get_health_poop_number_by_user_id(user_id, db, since, tz_name)
    records = health_poop_crud.get_health_poop_by_user_id(user_id, db, page_number, num_records, since, tz_name)
    return core_pagination.Page.build(records, total, page_number, num_records)


def get_health_poop(user_id: int, health_poop_id: int, db: Session) -> health_poop_schema.HealthPoopRead:
    """Return one of a user's poop records.

    Args:
        user_id: The record's owner.
        health_poop_id: The record to fetch.
        db: Database session.

    Returns:
        The record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    record = health_poop_crud.get_health_poop_by_id_and_user_id(health_poop_id, user_id, db)
    if record is None:
        raise core_exceptions.NotFoundError("Poop record not found")
    return record


def list_health_poop_by_date(user_id: int, date: str, db: Session) -> list[health_poop_schema.HealthPoopRead]:
    """Return a user's poop records for a calendar date in their own timezone.

    Args:
        user_id: The records' owner.
        date: The calendar date.
        db: Database session.

    Returns:
        The records of that date, newest first.
    """
    return health_poop_crud.get_health_poop_by_date_and_user_id(
        user_id, date, users_integration.resolve_timezone(user_id, db), db
    )


def create_health_poop(
    user_id: int, health_poop: health_poop_schema.HealthPoopCreate, db: Session
) -> health_poop_schema.HealthPoopRead:
    """Create a poop record and commit.

    Args:
        user_id: The record's owner.
        health_poop: The record to create.
        db: Database session.

    Returns:
        The created record.

    Raises:
        ConflictError: If the insert violates a database constraint.
    """
    created = health_poop_crud.create_health_poop(user_id, health_poop, db)
    db.commit()
    logger.info("Stored a bowel movement record", extra=core_logger.context(user_id=user_id))
    return created


def stage_import_health_poop(user_id: int, health_poop: health_poop_schema.HealthPoopCreate, db: Session) -> bool:
    """Stage an imported poop record unless the user already has one at that time.

    Args:
        user_id: The record's owner.
        health_poop: The record to import.
        db: Database session.

    Returns:
        True when the record was staged, False when the user already had it.
    """
    if health_poop_crud.health_poop_exists_at(user_id, health_poop.date_time, db):
        return False
    health_poop_crud.create_health_poop(user_id, health_poop, db)
    return True


def edit_health_poop(
    user_id: int, health_poop_id: int, health_poop: health_poop_schema.HealthPoopUpdate, db: Session, *, if_match: str
) -> health_poop_schema.HealthPoopRead:
    """Update a poop record, and commit.

    Args:
        user_id: The record's owner.
        health_poop_id: The record to change.
        health_poop: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    updated = health_record_service.commit_write(
        health_poop_crud.SPEC,
        health_poop_id,
        user_id,
        lambda: health_poop_crud.edit_health_poop(user_id, health_poop_id, health_poop, db, if_match=if_match),
        db,
        log_message="Edited a bowel movement record",
    )
    return updated


def delete_health_poop(user_id: int, health_poop_id: int, db: Session, *, if_match: str) -> None:
    """Delete a poop record and commit.

    Args:
        user_id: The record's owner.
        health_poop_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    health_record_service.commit_write(
        health_poop_crud.SPEC,
        health_poop_id,
        user_id,
        lambda: health_poop_crud.delete_health_poop(user_id, health_poop_id, db, if_match=if_match),
        db,
        log_message="Deleted a bowel movement record",
    )


def get_health_poop_chart(
    user_id: int, interval: health_constants.Interval, db: Session
) -> health_schema.HealthChartSeries:
    """Chart a user's daily bowel-movement frequency over an interval.

    Each value is the bucket's movements per day, so a week or month stays comparable with the daily target.
    The all-time window opens at the first movement, so its first month is not diluted by days before it.

    Args:
        user_id: The records' owner.
        interval: The window to chart.
        db: Database session.

    Returns:
        The interval's buckets, one point per bucket that holds a movement.
    """
    today = users_integration.local_today(user_id, db)
    since = health_computation.get_start_date_for_interval(interval.value, today)
    tz_name = users_integration.resolve_timezone(user_id, db)
    if interval is health_constants.Interval.ALL_TIME:
        since = health_poop_crud.get_health_poop_first_day(user_id, tz_name, db) or since
    bucket, counts = health_computation.chart_points(
        lambda bucket: health_poop_crud.get_health_poop_chart(user_id, since, bucket, tz_name, db)
    )
    points = [
        health_schema.HealthChartPoint(
            date=count.date,
            value=round(count.value / health_computation.bucket_day_count(count.date, bucket, since, today), 2),
        )
        for count in counts
    ]
    return health_schema.HealthChartSeries(bucket=bucket, points=points)
