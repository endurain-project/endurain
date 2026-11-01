"""Application logic for health fasting records.

Owns the one-active-fast rule, ending a fast, the statistics and streaks, the
ownership check, the timezone and interval resolution and the transaction
boundary. What other modules may consume lives in
:mod:`modules.health.health_fasting.integration_service`.
"""

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import core.timezone as core_timezone
import modules.health.constants as health_constants
import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.streaks as health_fasting_streaks
import modules.health.record_service as health_record_service
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def list_health_fasting(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    interval: health_constants.Interval | None = None,
) -> core_pagination.Page[health_fasting_schema.HealthFastingRead]:
    """List one page of a user's fasting records with their total.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page.
        num_records: Records per page.
        interval: Return only records within this interval.

    Returns:
        The page of records; ``total`` counts every record within the interval.
    """
    return health_record_service.list_page(
        user_id,
        interval,
        page_number,
        num_records,
        lambda since: health_fasting_crud.get_health_fasting_number_by_user_id(user_id, db, since),
        lambda since: health_fasting_crud.get_health_fasting_by_user_id(user_id, db, page_number, num_records, since),
        db,
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
        ConflictError: If the user already has an active fasting session.
    """
    if health_fasting_crud.get_active_fasting_by_user_id(user_id, db) is not None:
        raise core_exceptions.ConflictError(
            "User already has an active fasting session. Complete or cancel it before starting a new one."
        )

    created = health_fasting_crud.create_health_fasting(user_id, health_fasting, db)
    db.commit()
    logger.info("Stored a fasting session", extra=core_logger.context(user_id=user_id))
    return created


def stage_import_health_fasting(
    user_id: int, health_fasting: health_fasting_schema.HealthFastingCreate, db: Session
) -> bool:
    """Stage an imported fasting session unless the user already has it.

    A session counts as already there when the user has one that started at the same time. A running
    fast is skipped when the user already has one running, since only one may run at a time.

    Args:
        user_id: The session's owner.
        health_fasting: The session to import.
        db: Database session.

    Returns:
        True when the session was staged, False when it was skipped.
    """
    if health_fasting_crud.health_fasting_exists_at(user_id, health_fasting.fast_start_time, db):
        return False
    try:
        with db.begin_nested():
            health_fasting_crud.create_health_fasting(user_id, health_fasting, db)
    except core_exceptions.ConflictError:
        return False
    return True


def edit_health_fasting(
    user_id: int,
    health_fasting_id: int,
    health_fasting: health_fasting_schema.HealthFastingUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_fasting_schema.HealthFastingRead:
    """Update a fasting record, and commit.

    Args:
        user_id: The record's owner.
        health_fasting_id: The record to change.
        health_fasting: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    updated = health_record_service.commit_write(
        health_fasting_crud.SPEC,
        health_fasting_id,
        user_id,
        lambda: health_fasting_crud.edit_health_fasting(
            user_id, health_fasting_id, health_fasting, db, if_match=if_match
        ),
        db,
        log_message="Edited a fasting session",
    )
    return updated


def complete_health_fasting(
    user_id: int,
    health_fasting_id: int,
    complete_data: health_fasting_schema.HealthFastingComplete,
    db: Session,
    *,
    if_match: str,
) -> health_fasting_schema.HealthFastingRead:
    """End an in-progress fasting session, derive its duration, and commit.

    Args:
        user_id: The session's owner.
        health_fasting_id: The session to end.
        complete_data: End time, final status and optional notes.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The ended session.

    Raises:
        NotFoundError: If the user has no such session.
        ConflictError: If the session is not in progress.
        InvalidInputError: If the end time is before the start time.
        PreconditionFailedError: If the session changed since the client read it.
    """
    session = get_health_fasting(user_id, health_fasting_id, db)
    if session.status != health_fasting_schema.FastingStatus.IN_PROGRESS.value:
        raise core_exceptions.ConflictError("Fasting session is not in progress")

    start_time = core_timezone.to_utc_aware(session.fast_start_time)
    end_time = core_timezone.to_utc_aware(complete_data.fast_end_time)
    if end_time < start_time:
        raise core_exceptions.InvalidInputError("Fasting session cannot end before it started")

    ended = health_record_service.commit_write(
        health_fasting_crud.SPEC,
        health_fasting_id,
        user_id,
        lambda: health_fasting_crud.end_health_fasting(
            user_id,
            health_fasting_id,
            end_time,
            complete_data.status,
            int((end_time - start_time).total_seconds()),
            complete_data.notes,
            db,
            if_match=if_match,
        ),
        db,
        log_message="Completed a fasting session",
    )
    return ended


def delete_health_fasting(user_id: int, health_fasting_id: int, db: Session, *, if_match: str) -> None:
    """Delete a fasting record and commit.

    Args:
        user_id: The record's owner.
        health_fasting_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    health_record_service.commit_write(
        health_fasting_crud.SPEC,
        health_fasting_id,
        user_id,
        lambda: health_fasting_crud.delete_health_fasting(user_id, health_fasting_id, db, if_match=if_match),
        db,
        log_message="Deleted a fasting session",
    )
