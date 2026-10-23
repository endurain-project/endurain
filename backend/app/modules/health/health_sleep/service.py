"""Application logic for health sleep records.

Owns sleep scoring, the ownership check, the interval-to-date resolution and the
transaction boundary. What other modules may consume lives in
:mod:`modules.health.health_sleep.integration_service`.
"""

from datetime import date as date_type

from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.sleep_scoring as health_sleep_sleep_scoring
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


def list_health_sleep(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    interval: health_constants.Interval | None = None,
) -> health_sleep_schema.HealthSleepListResponse:
    """List a user's sleep records with their total.

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
    return health_sleep_schema.HealthSleepListResponse(
        total=health_sleep_crud.get_health_sleep_number_by_user_id(user_id, db, since),
        num_records=num_records,
        page_number=page_number,
        records=health_sleep_crud.get_health_sleep_by_user_id(user_id, db, page_number, num_records, since),
    )


def stage_edit_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepUpdate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Stage an update to a sleep record after checking it names the caller.

    Args:
        user_id: The record's owner.
        health_sleep: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the user has no such record.
    """
    if health_sleep.user_id != user_id:
        logger.warning("Refused to edit a sleep record of another user", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.PermissionDeniedError("Cannot edit health sleep for another user.")
    return health_sleep_crud.edit_health_sleep(user_id, health_sleep, db)


def stage_upsert_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepCreate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Stage a sleep record, or an update to the user's record for the same date.

    The record is stored as given: scoring is the caller's business.

    A writer that creates the date first, on this replica or another, is not an error: the
    record it created is updated instead.

    Args:
        user_id: The record's owner.
        health_sleep: The record to store.
        db: Database session.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    if health_sleep.date is None:
        # The request carries no timezone, so the fallback is the server's configured zone.
        health_sleep.date = core_timezone.today_in(core_config.settings.TZ)

    existing = health_sleep_crud.get_health_sleep_by_date_and_user_id(user_id, health_sleep.date.isoformat(), db)
    if existing is None:
        try:
            with db.begin_nested():
                return health_sleep_crud.create_health_sleep(user_id, health_sleep, db)
        except core_exceptions.ConflictError:
            existing = health_sleep_crud.get_health_sleep_by_date_and_user_id(
                user_id, health_sleep.date.isoformat(), db
            )
            if existing is None:
                raise
    return stage_edit_health_sleep(
        user_id,
        health_sleep_schema.HealthSleepUpdate(id=existing.id, user_id=user_id, **health_sleep.model_dump()),
        db,
    )


def create_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepCreate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Score a sleep record, then create it or update the user's record for the same date, and commit.

    Args:
        user_id: The record's owner.
        health_sleep: The record to store.
        db: Database session.

    Returns:
        The stored record.

    Raises:
        ConflictError: If the date's record cannot be created or found.
    """
    health_sleep_sleep_scoring.calculate_and_set_sleep_scores(health_sleep)
    stored = stage_upsert_health_sleep(user_id, health_sleep, db)
    db.commit()
    logger.info("Stored a sleep record", extra=core_logger.context(user_id=user_id))
    return stored


def edit_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepUpdate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Score and update a sleep record, and commit.

    Args:
        user_id: The record's owner.
        health_sleep: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the user has no such record.
    """
    health_sleep_sleep_scoring.calculate_and_set_sleep_scores(health_sleep)
    updated = stage_edit_health_sleep(user_id, health_sleep, db)
    db.commit()
    logger.info("Edited a sleep record", extra=core_logger.context(user_id=user_id))
    return updated


def delete_health_sleep(user_id: int, health_sleep_id: int, db: Session) -> None:
    """Delete a sleep record and commit.

    Args:
        user_id: The record's owner.
        health_sleep_id: The record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    health_sleep_crud.delete_health_sleep(user_id, health_sleep_id, db)
    db.commit()
    logger.info("Deleted a sleep record", extra=core_logger.context(user_id=user_id, health_sleep_id=health_sleep_id))
