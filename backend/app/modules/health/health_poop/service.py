"""Application logic for health poop (bowel movement) records.

Owns the ownership check, the timezone and interval resolution and the
transaction boundary. What other modules may consume lives in
:mod:`modules.health.health_poop.integration_service`.
"""

from datetime import date as date_type

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.schema as health_poop_schema
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


def list_health_poop(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    interval: health_constants.Interval | None = None,
) -> health_poop_schema.HealthPoopListResponse:
    """List a user's poop records with their total.

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
    return health_poop_schema.HealthPoopListResponse(
        total=health_poop_crud.get_health_poop_number_by_user_id(user_id, db, since),
        num_records=num_records,
        page_number=page_number,
        records=health_poop_crud.get_health_poop_by_user_id(user_id, db, page_number, num_records, since),
    )


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


def edit_health_poop(
    user_id: int, health_poop: health_poop_schema.HealthPoopUpdate, db: Session
) -> health_poop_schema.HealthPoopRead:
    """Update a poop record after checking it names the caller, and commit.

    Args:
        user_id: The record's owner.
        health_poop: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the user has no such record.
    """
    if health_poop.user_id != user_id:
        logger.warning(
            "Refused to edit a bowel movement record of another user", extra=core_logger.context(user_id=user_id)
        )
        raise core_exceptions.PermissionDeniedError("Cannot edit health poop record for another user.")

    updated = health_poop_crud.edit_health_poop(user_id, health_poop, db)
    db.commit()
    logger.info("Edited a bowel movement record", extra=core_logger.context(user_id=user_id))
    return updated


def delete_health_poop(user_id: int, health_poop_id: int, db: Session) -> None:
    """Delete a poop record and commit.

    Args:
        user_id: The record's owner.
        health_poop_id: The record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    health_poop_crud.delete_health_poop(user_id, health_poop_id, db)
    db.commit()
    logger.info(
        "Deleted a bowel movement record", extra=core_logger.context(user_id=user_id, health_poop_id=health_poop_id)
    )
