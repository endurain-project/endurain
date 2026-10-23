"""Application logic for health fasting records.

Owns the one-active-fast rule, ending a fast, the statistics and streaks, the
ownership check, the timezone and interval resolution and the transaction
boundary. What other modules may consume lives in
:mod:`modules.health.health_fasting.integration_service`.
"""

from datetime import date as date_type

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.streaks as health_fasting_streaks
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


def list_health_fasting(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    interval: health_constants.Interval | None = None,
) -> health_fasting_schema.HealthFastingListResponse:
    """List a user's fasting records with their total.

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
    return health_fasting_schema.HealthFastingListResponse(
        total=health_fasting_crud.get_health_fasting_number_by_user_id(user_id, db, since),
        num_records=num_records,
        page_number=page_number,
        records=health_fasting_crud.get_health_fasting_by_user_id(user_id, db, page_number, num_records, since),
    )


def get_health_fasting(user_id: int, health_fasting_id: int, db: Session) -> health_fasting_schema.HealthFastingRead:
    """Return one of a user's fasting records.

    Args:
        user_id: The record's owner.
        health_fasting_id: The record to fetch.
        db: Database session.

    Returns:
        The record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    record = health_fasting_crud.get_health_fasting_by_id_and_user_id(health_fasting_id, user_id, db)
    if record is None:
        raise core_exceptions.NotFoundError("Fasting record not found")
    return record


def get_active_fasting(user_id: int, db: Session) -> health_fasting_schema.HealthFastingRead | None:
    """Return a user's in-progress fasting session, or ``None``.

    Args:
        user_id: The session's owner.
        db: Database session.

    Returns:
        The active session, or ``None``.
    """
    return health_fasting_crud.get_active_fasting_by_user_id(user_id, db)


def get_fasting_stats(user_id: int, db: Session) -> health_fasting_schema.HealthFastingStatsResponse:
    """Compute a user's fasting statistics.

    Args:
        user_id: The statistics' owner.
        db: Database session.

    Returns:
        Totals, averages, streaks and the completion rate.
    """
    total_fasts = health_fasting_crud.get_completed_fasting_count(user_id, db)
    completed_dates = health_fasting_crud.get_completed_fasting_dates_by_user_id(
        user_id, users_integration.resolve_timezone(user_id, db), db
    )
    current_streak, longest_streak = health_fasting_streaks.calculate_streaks(
        completed_dates, users_integration.local_today(user_id, db)
    )
    total_started = health_fasting_crud.get_health_fasting_number_by_user_id(user_id, db)
    completion_rate = (total_fasts / total_started * 100) if total_started > 0 else 0.0

    return health_fasting_schema.HealthFastingStatsResponse(
        total_fasts=total_fasts,
        current_streak=current_streak,
        longest_streak=longest_streak,
        avg_duration_seconds=health_fasting_crud.get_avg_fasting_duration(user_id, db),
        total_fasting_seconds=health_fasting_crud.get_total_fasting_seconds(user_id, db),
        completion_rate=round(completion_rate, 1),
    )


def create_health_fasting(
    user_id: int, health_fasting: health_fasting_schema.HealthFastingCreate, db: Session
) -> health_fasting_schema.HealthFastingRead:
    """Start a fasting session and commit, unless the user already has one running.

    Args:
        user_id: The session's owner.
        health_fasting: The session to create.
        db: Database session.

    Returns:
        The created session.

    Raises:
        InvalidInputError: If the user already has an active fasting session.
    """
    if health_fasting_crud.get_active_fasting_by_user_id(user_id, db) is not None:
        raise core_exceptions.InvalidInputError(
            "User already has an active fasting session. Complete or cancel it before starting a new one."
        )

    created = health_fasting_crud.create_health_fasting(user_id, health_fasting, db)
    db.commit()
    logger.info("Stored a fasting session", extra=core_logger.context(user_id=user_id))
    return created


def edit_health_fasting(
    user_id: int, health_fasting: health_fasting_schema.HealthFastingUpdate, db: Session
) -> health_fasting_schema.HealthFastingRead:
    """Update a fasting record after checking it names the caller, and commit.

    Args:
        user_id: The record's owner.
        health_fasting: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the user has no such record.
    """
    if health_fasting.user_id != user_id:
        logger.warning("Refused to edit a fasting session of another user", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.PermissionDeniedError("Cannot edit fasting record for another user.")

    updated = health_fasting_crud.edit_health_fasting(user_id, health_fasting, db)
    db.commit()
    logger.info("Edited a fasting session", extra=core_logger.context(user_id=user_id))
    return updated


def complete_health_fasting(
    user_id: int,
    health_fasting_id: int,
    complete_data: health_fasting_schema.HealthFastingComplete,
    db: Session,
) -> health_fasting_schema.HealthFastingRead:
    """End an in-progress fasting session, derive its duration, and commit.

    Args:
        user_id: The session's owner.
        health_fasting_id: The session to end.
        complete_data: End time, final status and optional notes.
        db: Database session.

    Returns:
        The ended session.

    Raises:
        NotFoundError: If the user has no such session.
        InvalidInputError: If the session is not in progress.
    """
    session = get_health_fasting(user_id, health_fasting_id, db)
    if session.status != health_fasting_schema.FastingStatus.IN_PROGRESS.value:
        raise core_exceptions.InvalidInputError("Fasting session is not in progress")

    start_time = core_timezone.to_utc_aware(session.fast_start_time)
    end_time = core_timezone.to_utc_aware(complete_data.fast_end_time)

    ended = health_fasting_crud.end_health_fasting(
        user_id,
        health_fasting_id,
        end_time,
        complete_data.status,
        int((end_time - start_time).total_seconds()),
        complete_data.notes,
        db,
    )
    db.commit()
    logger.info(
        "Completed a fasting session", extra=core_logger.context(user_id=user_id, health_fasting_id=health_fasting_id)
    )
    return ended


def delete_health_fasting(user_id: int, health_fasting_id: int, db: Session) -> None:
    """Delete a fasting record and commit.

    Args:
        user_id: The record's owner.
        health_fasting_id: The record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    health_fasting_crud.delete_health_fasting(user_id, health_fasting_id, db)
    db.commit()
    logger.info(
        "Deleted a fasting session", extra=core_logger.context(user_id=user_id, health_fasting_id=health_fasting_id)
    )
