"""Application logic for health steps records.

Owns the ownership check, the interval-to-date resolution and the transaction
boundary. What other modules may consume lives in
:mod:`modules.health.health_steps.integration_service`.
"""

from datetime import date as date_type

from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.schema as health_steps_schema
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


def list_health_steps(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    interval: health_constants.Interval | None = None,
) -> health_steps_schema.HealthStepsListResponse:
    """List a user's steps records with their total.

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
    return health_steps_schema.HealthStepsListResponse(
        total=health_steps_crud.get_health_steps_number_by_user_id(user_id, db, since),
        num_records=num_records,
        page_number=page_number,
        records=health_steps_crud.get_health_steps_by_user_id(user_id, db, page_number, num_records, since),
    )


def stage_edit_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthStepsUpdate, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Stage an update to a steps record after checking it names the caller.

    Args:
        user_id: The record's owner.
        health_steps: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the user has no such record.
    """
    if health_steps.user_id != user_id:
        logger.warning("Refused to edit a steps record of another user", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.PermissionDeniedError("Cannot edit health steps for another user.")
    return health_steps_crud.edit_health_steps(user_id, health_steps, db)


def stage_upsert_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthStepsCreate, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Stage a steps record, or an update to the user's record for the same date.

    A writer that creates the date first, on this replica or another, is not an error: the
    record it created is updated instead.

    Args:
        user_id: The record's owner.
        health_steps: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    if health_steps.date is None:
        # The request carries no timezone, so the fallback is the server's configured zone.
        health_steps.date = core_timezone.today_in(core_config.settings.TZ)

    existing = health_steps_crud.get_health_steps_by_date_and_user_id(user_id, health_steps.date.isoformat(), db)
    if existing is None:
        try:
            with db.begin_nested():
                return health_steps_crud.create_health_steps(user_id, health_steps, db)
        except core_exceptions.ConflictError:
            existing = health_steps_crud.get_health_steps_by_date_and_user_id(
                user_id, health_steps.date.isoformat(), db
            )
            if existing is None:
                raise
    return stage_edit_health_steps(
        user_id,
        health_steps_schema.HealthStepsUpdate(id=existing.id, user_id=user_id, **health_steps.model_dump()),
        db,
    )


def create_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthStepsCreate, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Create a steps record, or update the user's record for the same date, and commit.

    Args:
        user_id: The record's owner.
        health_steps: The record to store.
        db: Database session.

    Returns:
        The stored record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    stored = stage_upsert_health_steps(user_id, health_steps, db)
    db.commit()
    logger.info("Stored a steps record", extra=core_logger.context(user_id=user_id))
    return stored


def edit_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthStepsUpdate, db: Session
) -> health_steps_schema.HealthStepsRead:
    """Update a steps record and commit.

    Args:
        user_id: The record's owner.
        health_steps: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the user has no such record.
    """
    updated = stage_edit_health_steps(user_id, health_steps, db)
    db.commit()
    logger.info("Edited a steps record", extra=core_logger.context(user_id=user_id))
    return updated


def delete_health_steps(user_id: int, health_steps_id: int, db: Session) -> None:
    """Delete a steps record and commit.

    Args:
        user_id: The record's owner.
        health_steps_id: The record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    health_steps_crud.delete_health_steps(user_id, health_steps_id, db)
    db.commit()
    logger.info("Deleted a steps record", extra=core_logger.context(user_id=user_id, health_steps_id=health_steps_id))
