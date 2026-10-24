"""Application logic for health water intake records.

Owns the ownership check, the same-day accumulation, the interval-to-date
resolution and the transaction boundary. What other modules may consume lives in
:mod:`modules.health.health_water.integration_service`.
"""

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.schema as health_water_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def _since(user_id: int, interval: health_constants.Interval | None, db: Session) -> date_type | None:
    """Return the first date of an interval in the user's own calendar, or ``None``.

    Args:
        user_id: The user whose "today" anchors the interval.
        interval: The interval to resolve.
        db: Database session.

    Returns:
        The interval's start date, or ``None`` when no interval is given.
    """
    if interval is None:
        return None
    return health_computation.get_start_date_for_interval(interval.value, users_integration.local_today(user_id, db))


def list_health_water(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    interval: health_constants.Interval | None = None,
) -> health_water_schema.HealthWaterListResponse:
    """List a user's water intake records with their total.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page.
        num_records: Records per page.
        interval: Return only records within this interval.

    Returns:
        The page of records and the total.
    """
    since = _since(user_id, interval, db)
    return health_water_schema.HealthWaterListResponse(
        total=health_water_crud.get_health_water_number_by_user_id(user_id, db, since),
        num_records=num_records,
        page_number=page_number,
        records=health_water_crud.get_health_water_by_user_id(user_id, db, page_number, num_records, since),
    )


def stage_edit_health_water(
    user_id: int, health_water: health_water_schema.HealthWaterUpdate, db: Session
) -> health_water_schema.HealthWaterRead:
    """Stage an update to a water intake record after checking it names the caller.

    Args:
        user_id: The record's owner.
        health_water: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the user has no such record.
    """
    if health_water.user_id != user_id:
        logger.warning(
            "Refused to edit a water intake record of another user", extra=core_logger.context(user_id=user_id)
        )
        raise core_exceptions.PermissionDeniedError("Cannot edit health water intake for another user.")
    return health_water_crud.edit_health_water(user_id, health_water, db)


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
        # The request carries no timezone, so the fallback is the server's configured zone.
        health_water.date = core_timezone.today_in(core_config.settings.TZ)

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
    user_id: int, health_water: health_water_schema.HealthWaterUpdate, db: Session
) -> health_water_schema.HealthWaterRead:
    """Update a water intake record and commit.

    Args:
        user_id: The record's owner.
        health_water: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the user has no such record.
    """
    updated = stage_edit_health_water(user_id, health_water, db)
    db.commit()
    logger.info("Edited a water intake record", extra=core_logger.context(user_id=user_id))
    return updated


def delete_health_water(user_id: int, health_water_id: int, db: Session) -> None:
    """Delete a water intake record and commit.

    Args:
        user_id: The record's owner.
        health_water_id: The record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    health_water_crud.delete_health_water(user_id, health_water_id, db)
    db.commit()
    logger.info(
        "Deleted a water intake record", extra=core_logger.context(user_id=user_id, health_water_id=health_water_id)
    )
