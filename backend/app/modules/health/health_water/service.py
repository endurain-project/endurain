"""Application logic for health water intake records.

Owns the ownership check, the same-day accumulation, the interval-to-date
resolution and the transaction boundary. What other modules may consume lives in
:mod:`modules.health.health_water.integration_service`.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.schema as health_water_schema
import modules.health.record_service as health_record_service
import modules.health.schema as health_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def list_health_water(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    interval: health_constants.Interval | None = None,
) -> core_pagination.Page[health_water_schema.HealthWaterRead]:
    """List one page of a user's water records with their total.

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
    total = health_water_crud.get_health_water_number_by_user_id(user_id, db, since)
    records = health_water_crud.get_health_water_by_user_id(user_id, db, page_number, num_records, since)
    return core_pagination.Page.build(records, total, page_number, num_records)


def stage_edit_health_water(
    user_id: int,
    health_water_id: int,
    health_water: health_water_schema.HealthWaterUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_water_schema.HealthWaterRead:
    """Stage an update to a water intake record.

    Args:
        user_id: The record's owner.
        health_water_id: The record to change.
        health_water: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    return health_water_crud.edit_health_water(user_id, health_water_id, health_water, db, if_match=if_match)


def stage_add_health_water(
    user_id: int, health_water: health_water_schema.HealthWaterCreate, db: Session
) -> health_water_schema.HealthWaterRead:
    """Stage an intake added to the user's total for its date, creating the day's record if needed.

    A writer that creates the date first, on this replica or another, is not an error: the
    intake is added to the record it created.

    Args:
        user_id: The record's owner.
        health_water: The intake to add.
        db: Database session.

    Returns:
        The staged record of the day.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    if health_water.date is None:
        # The request carries no timezone, so the day is the athlete's own.
        health_water.date = users_integration.local_today(user_id, db)

    existing = health_water_crud.get_health_water_by_date_and_user_id(user_id, health_water.date.isoformat(), db)
    if existing is None:
        try:
            with db.begin_nested():
                return health_water_crud.create_health_water(user_id, health_water, db)
        except core_exceptions.ConflictError:
            existing = health_water_crud.get_health_water_by_date_and_user_id(
                user_id, health_water.date.isoformat(), db
            )
            if existing is None:
                raise
    return health_water_crud.add_health_water_amount(
        user_id, existing.id, health_water.amount_ml or Decimal(0), health_water.source, db
    )


def stage_upsert_health_water(
    user_id: int, health_water: health_water_schema.HealthWaterCreate, db: Session
) -> health_water_schema.HealthWaterRead:
    """Stage a water record, or replace the amount of the user's record for the same date.

    Unlike :func:`stage_add_health_water` the amount is stored as given, so writing the same
    record twice leaves the day unchanged.

    A writer that creates the date first, on this replica or another, is not an error: the
    record it created is updated instead.

    Args:
        user_id: The record's owner.
        health_water: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    if health_water.date is None:
        # The request carries no timezone, so the day is the athlete's own.
        health_water.date = users_integration.local_today(user_id, db)

    day = health_water.date.isoformat()
    update = health_water_schema.HealthWaterUpdate(**health_water.model_dump())
    return health_computation.upsert_for_day(
        find=lambda: health_water_crud.get_health_water_by_date_and_user_id(user_id, day, db),
        create=lambda: health_water_crud.create_health_water(user_id, health_water, db),
        edit=lambda record_id: stage_edit_health_water(user_id, record_id, update, db, if_match="*"),
        db=db,
    )


def create_health_water(
    user_id: int, health_water: health_water_schema.HealthWaterCreate, db: Session
) -> health_water_schema.HealthWaterRead:
    """Add an intake to the user's total for its date, creating the day's record if needed, and commit.

    Args:
        user_id: The record's owner.
        health_water: The intake to add.
        db: Database session.

    Returns:
        The day's record after the addition.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    stored = stage_add_health_water(user_id, health_water, db)
    db.commit()
    logger.info("Stored a water intake record", extra=core_logger.context(user_id=user_id))
    return stored


def edit_health_water(
    user_id: int,
    health_water_id: int,
    health_water: health_water_schema.HealthWaterUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_water_schema.HealthWaterRead:
    """Update a water intake record and commit.

    Args:
        user_id: The record's owner.
        health_water_id: The record to change.
        health_water: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    updated = health_record_service.commit_write(
        health_water_crud.SPEC,
        health_water_id,
        user_id,
        lambda: stage_edit_health_water(user_id, health_water_id, health_water, db, if_match=if_match),
        db,
        log_message="Edited a water intake record",
    )
    return updated


def delete_health_water(user_id: int, health_water_id: int, db: Session, *, if_match: str) -> None:
    """Delete a water intake record and commit.

    Args:
        user_id: The record's owner.
        health_water_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    health_record_service.commit_write(
        health_water_crud.SPEC,
        health_water_id,
        user_id,
        lambda: health_water_crud.delete_health_water(user_id, health_water_id, db, if_match=if_match),
        db,
        log_message="Deleted a water intake record",
    )


def get_health_water_chart(
    user_id: int, interval: health_constants.Interval, db: Session
) -> health_schema.HealthChartSeries:
    """Chart a user's water intake over an interval.

    Args:
        user_id: The records' owner.
        interval: The window to chart.
        db: Database session.

    Returns:
        The interval's buckets, one point per bucket that holds a value.
    """
    return health_record_service.chart(
        user_id,
        interval,
        lambda since, bucket: health_water_crud.get_health_water_chart(user_id, since, bucket, db),
        db,
    )
