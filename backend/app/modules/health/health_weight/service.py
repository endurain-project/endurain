"""Application logic for health weight records.

Owns the BMI rule (it needs the user's height), the ownership check, the
interval-to-date resolution and the transaction boundary. What other modules may
consume lives in :mod:`modules.health.health_weight.integration_service`.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import core.pagination as core_pagination
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_weight.bmi as health_weight_bmi
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.schema as health_weight_schema
import modules.health.record_service as health_record_service
import modules.health.schema as health_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def _user_height_cm(user_id: int, db: Session) -> float | None:
    """Return the user's height in centimeters, or ``None`` when unknown.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The height, or ``None``.
    """
    user = users_integration.get_user(user_id, db)
    return float(user.height) if user is not None and user.height is not None else None


def _with_bmi[RecordT: health_weight_schema.HealthWeightCreate | health_weight_schema.HealthWeightUpdate](
    health_weight: RecordT, user_id: int, db: Session
) -> RecordT:
    """Return the record with its BMI derived from the user's height.

    Args:
        health_weight: The record to complete.
        user_id: The record's owner.
        db: Database session.

    Returns:
        A copy carrying the calculated BMI.
    """
    bmi = health_weight_bmi.calculate_bmi(health_weight.weight, _user_height_cm(user_id, db))
    return health_weight.model_copy(update={"bmi": bmi})


def list_health_weight(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    interval: health_constants.Interval | None = None,
) -> core_pagination.Page[health_weight_schema.HealthWeightRead]:
    """List one page of a user's weight records with their total.

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
    total = health_weight_crud.get_health_weight_number_by_user_id(user_id, db, since)
    records = health_weight_crud.get_health_weight_by_user_id(user_id, db, page_number, num_records, since)
    return core_pagination.Page.build(records, total, page_number, num_records)


def stage_create_health_weight(
    user_id: int, health_weight: health_weight_schema.HealthWeightCreate, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Stage a new weight record, deriving the BMI when it is not given.

    Args:
        user_id: The record's owner.
        health_weight: The record to create.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    if health_weight.bmi is None:
        health_weight = _with_bmi(health_weight, user_id, db)
    return health_weight_crud.create_health_weight(user_id, health_weight, db)


def stage_edit_health_weight(
    user_id: int,
    health_weight_id: int,
    health_weight: health_weight_schema.HealthWeightUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_weight_schema.HealthWeightRead:
    """Stage an update to a weight record, deriving the BMI when it is not given.

    Args:
        user_id: The record's owner.
        health_weight_id: The record to change.
        health_weight: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    if health_weight.bmi is None and health_weight.weight is not None:
        health_weight = _with_bmi(health_weight, user_id, db)
    return health_weight_crud.edit_health_weight(user_id, health_weight_id, health_weight, db, if_match=if_match)


def stage_upsert_health_weight(
    user_id: int, health_weight: health_weight_schema.HealthWeightCreate, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Stage a weight record, or an update to the user's record for the same date.

    A writer that creates the date first, on this replica or another, is not an error: the
    record it created is updated instead.

    Args:
        user_id: The record's owner.
        health_weight: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    if health_weight.date is None:
        # The request carries no timezone, so the day is the athlete's own.
        health_weight.date = users_integration.local_today(user_id, db)

    day = health_weight.date.isoformat()
    update = health_weight_schema.HealthWeightUpdate(**health_weight.model_dump())
    return health_computation.upsert_for_day(
        find=lambda: health_weight_crud.get_health_weight_by_date_and_user_id(user_id, day, db),
        create=lambda: stage_create_health_weight(user_id, health_weight, db),
        edit=lambda record_id: stage_edit_health_weight(user_id, record_id, update, db, if_match="*"),
        db=db,
    )


def create_health_weight(
    user_id: int, health_weight: health_weight_schema.HealthWeightCreate, db: Session
) -> health_weight_schema.HealthWeightRead:
    """Create a weight record for the user's day, and commit.

    Args:
        user_id: The record's owner.
        health_weight: The record to create; a missing date is the user's local today.
        db: Database session.

    Returns:
        The created record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    if health_weight.date is None:
        health_weight.date = users_integration.local_today(user_id, db)
    created = stage_create_health_weight(user_id, health_weight, db)
    db.commit()
    logger.info("Stored a weight record", extra=core_logger.context(user_id=user_id))
    return created


def edit_health_weight(
    user_id: int,
    health_weight_id: int,
    health_weight: health_weight_schema.HealthWeightUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_weight_schema.HealthWeightRead:
    """Update a weight record and commit.

    Args:
        user_id: The record's owner.
        health_weight_id: The record to change.
        health_weight: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    updated = health_record_service.commit_write(
        health_weight_crud.SPEC,
        health_weight_id,
        user_id,
        lambda: stage_edit_health_weight(user_id, health_weight_id, health_weight, db, if_match=if_match),
        db,
        log_message="Edited a weight record",
    )
    return updated


def delete_health_weight(user_id: int, health_weight_id: int, db: Session, *, if_match: str) -> None:
    """Delete a weight record and commit.

    Args:
        user_id: The record's owner.
        health_weight_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    health_record_service.commit_write(
        health_weight_crud.SPEC,
        health_weight_id,
        user_id,
        lambda: health_weight_crud.delete_health_weight(user_id, health_weight_id, db, if_match=if_match),
        db,
        log_message="Deleted a weight record",
    )


def get_health_weight_chart(
    user_id: int, interval: health_constants.Interval, db: Session
) -> health_schema.HealthChartSeries:
    """Chart a user's weight over an interval.

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
        lambda since, bucket: health_weight_crud.get_health_weight_chart(user_id, since, bucket, db),
        db,
    )
