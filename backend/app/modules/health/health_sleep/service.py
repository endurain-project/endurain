"""Application logic for health sleep records.

Owns sleep scoring, the ownership check, the interval-to-date resolution and the
transaction boundary. What other modules may consume lives in
:mod:`modules.health.health_sleep.integration_service`.
"""

from datetime import date as date_type

from sqlalchemy.orm import Session

import core.etag as core_etag
import core.logger as core_logger
import core.pagination as core_pagination
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
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    interval: health_constants.Interval | None = None,
) -> core_pagination.Page[health_sleep_schema.HealthSleepRead]:
    """List one page of a user's sleep records with their total.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page.
        num_records: Records per page.
        interval: Return only records within this interval.

    Returns:
        The page of records; ``total`` counts every record within the interval.
    """
    since = _since(user_id, interval, db)
    total = health_sleep_crud.get_health_sleep_number_by_user_id(user_id, db, since)
    records = health_sleep_crud.get_health_sleep_by_user_id(user_id, db, page_number, num_records, since)
    return core_pagination.Page.build(records, total, page_number, num_records)


def stage_edit_health_sleep(
    user_id: int,
    health_sleep_id: int,
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_sleep_schema.HealthSleepRead:
    """Stage an update to a sleep record.

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
        PreconditionFailedError: If the record changed since the client read it.
    """
    return health_sleep_crud.edit_health_sleep(user_id, health_sleep_id, health_sleep, db, if_match=if_match)


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
        # The request carries no timezone, so the day is the athlete's own.
        health_sleep.date = users_integration.local_today(user_id, db)

    day = health_sleep.date.isoformat()
    update = health_sleep_schema.HealthSleepUpdate(**health_sleep.model_dump())
    return health_computation.upsert_for_day(
        find=lambda: health_sleep_crud.get_health_sleep_by_date_and_user_id(user_id, day, db),
        create=lambda: health_sleep_crud.create_health_sleep(user_id, health_sleep, db),
        edit=lambda record_id: stage_edit_health_sleep(user_id, record_id, update, db, if_match="*"),
        db=db,
    )


def create_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleepCreate, db: Session
) -> health_sleep_schema.HealthSleepRead:
    """Create a sleep record for the user's day, and commit.

    Args:
        user_id: The record's owner.
        health_sleep: The record to create; a missing date is the user's local today.
        db: Database session.

    Returns:
        The created record.

    Raises:
        ConflictError: If the user already has a record for that date.
    """
    if health_sleep.date is None:
        health_sleep.date = users_integration.local_today(user_id, db)
    health_sleep_sleep_scoring.calculate_and_set_sleep_scores(health_sleep)
    created = health_sleep_crud.create_health_sleep(user_id, health_sleep, db)
    db.commit()
    logger.debug("Stored a sleep record", extra=core_logger.context(user_id=user_id))
    return created


def edit_health_sleep(
    user_id: int,
    health_sleep_id: int,
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_sleep_schema.HealthSleepRead:
    """Score and update a sleep record, and commit.

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
        PreconditionFailedError: If the record changed since the client read it.
    """
    health_sleep_sleep_scoring.calculate_and_set_sleep_scores(health_sleep)
    with core_etag.refuse_stale_write(
        db,
        "sleep record",
        lambda: health_sleep_crud.health_sleep_exists(health_sleep_id, user_id, db),
        "Sleep record not found",
    ):
        updated = stage_edit_health_sleep(user_id, health_sleep_id, health_sleep, db, if_match=if_match)
        db.commit()
    logger.debug("Edited a sleep record", extra=core_logger.context(user_id=user_id))
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
    logger.debug("Deleted a sleep record", extra=core_logger.context(user_id=user_id, health_sleep_id=health_sleep_id))
