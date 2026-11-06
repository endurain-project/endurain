"""Application logic for health fasting records.

Owns the one-active-fast rule, ending a fast, the statistics and streaks, the
ownership check, the timezone and interval resolution and the transaction
boundary. What other modules may consume lives in
:mod:`modules.health.health_fasting.integration_service`.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

import core.date_range as core_date_range
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
import modules.users.users_profile.contracts as users_profile_contracts

logger = core_logger.get_logger(__name__)

#: Fields an archive carries that the server derives on write; they are dropped on import.
_SERVER_DERIVED = frozenset({"actual_duration_seconds"})

_OVERLAP_MESSAGE = "Another fasting session overlaps these times"

_ENDED_STATUSES = frozenset(
    {health_fasting_schema.FastingStatus.COMPLETED.value, health_fasting_schema.FastingStatus.BROKEN.value}
)


def _seconds_between(fast_start_time: datetime, fast_end_time: datetime) -> int:
    """Return how long a fast lasted.

    Args:
        fast_start_time: When the fast started.
        fast_end_time: When the fast ended.

    Returns:
        The seconds between the two times.
    """
    return int(
        (core_timezone.to_utc_aware(fast_end_time) - core_timezone.to_utc_aware(fast_start_time)).total_seconds()
    )


def _duration_seconds(fast_start_time: datetime, fast_end_time: datetime | None) -> int | None:
    """Return the duration a fast stores.

    Args:
        fast_start_time: When the fast started.
        fast_end_time: When the fast ended, or ``None`` while it has not.

    Returns:
        The seconds between the two times, or ``None`` without an end time.
    """
    return None if fast_end_time is None else _seconds_between(fast_start_time, fast_end_time)


def _check_times(fast_start_time: datetime, fast_end_time: datetime | None, status: str | None) -> None:
    """Refuse times and a status that cannot describe one fast.

    A running fast has no end time, and a completed or broken one has one; a cancelled one may have either.

    Args:
        fast_start_time: When the fast started.
        fast_end_time: When the fast ended, or ``None``.
        status: The fast's status.

    Raises:
        InvalidInputError: If the fast ends before it started, is completed or broken without an end, or is
            in progress with an end.
    """
    if fast_end_time is None:
        if status in _ENDED_STATUSES:
            raise core_exceptions.InvalidInputError("A completed or broken fasting session needs an end time")
    elif status == health_fasting_schema.FastingStatus.IN_PROGRESS.value:
        raise core_exceptions.InvalidInputError("A fasting session in progress cannot have an end time")
    elif core_timezone.to_utc_aware(fast_end_time) < core_timezone.to_utc_aware(fast_start_time):
        raise core_exceptions.InvalidInputError("Fasting session cannot end before it started")


def _overlaps(
    user_id: int,
    fast_start_time: datetime,
    fast_end_time: datetime | None,
    status: str | None,
    db: Session,
    *,
    exclude_id: int | None = None,
) -> bool:
    """Tell whether another fast of the user overlaps the times.

    A fast without an end time lasts indefinitely only while it is in progress; a cancelled one has no
    extent to overlap with.

    Args:
        user_id: The fast's owner.
        fast_start_time: When the fast started.
        fast_end_time: When the fast ended, or ``None``.
        status: The fast's status.
        db: Database session.
        exclude_id: The fast being edited, which does not overlap itself.

    Returns:
        True when another fast overlaps.
    """
    if fast_end_time is None and status != health_fasting_schema.FastingStatus.IN_PROGRESS.value:
        return False
    return health_fasting_crud.fasting_overlaps(
        user_id,
        core_timezone.to_utc_aware(fast_start_time),
        core_timezone.to_utc_aware(fast_end_time),
        db,
        exclude_id=exclude_id,
    )


def list_health_fasting(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    interval: health_constants.Interval | None = None,
    date_range: core_date_range.DateRange = core_date_range.DateRange(),
) -> core_pagination.Page[health_fasting_schema.HealthFastingRead]:
    """List one page of a user's fasting records with their total.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page.
        num_records: Records per page.
        interval: Return only records within this interval, looking back from today; ignored when
            ``date_range`` is set.
        date_range: Return only records within these inclusive dates instead of the interval.

    Returns:
        The page of records; ``total`` counts every record within the window.
    """
    return health_record_service.list_page(
        user_id,
        interval,
        date_range,
        page_number,
        num_records,
        lambda since, until: health_fasting_crud.get_health_fasting_number_by_user_id(user_id, db, since, until),
        lambda since, until: health_fasting_crud.get_health_fasting_by_user_id(
            user_id, db, page_number, num_records, since, until
        ),
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
        ConflictError: If the user already has an active fasting session, or another session overlaps the times.
        InvalidInputError: If the session ends before it started, is completed or broken without an end, or is
            in progress with an end.
    """
    if health_fasting_crud.get_active_fasting_by_user_id(user_id, db) is not None:
        raise core_exceptions.ConflictError(
            "User already has an active fasting session. Complete or cancel it before starting a new one."
        )
    _check_times(health_fasting.fast_start_time, health_fasting.fast_end_time, health_fasting.status)
    if _overlaps(user_id, health_fasting.fast_start_time, health_fasting.fast_end_time, health_fasting.status, db):
        raise core_exceptions.ConflictError(_OVERLAP_MESSAGE)

    created = health_fasting_crud.create_health_fasting(
        user_id,
        health_fasting_schema.HealthFastingImport(
            **health_fasting.model_dump(), source=health_fasting_schema.Source.MANUAL
        ),
        db,
        actual_duration_seconds=_duration_seconds(health_fasting.fast_start_time, health_fasting.fast_end_time),
    )
    db.commit()
    logger.info("Stored a fasting session", extra=core_logger.context(user_id=user_id))
    return created


def stage_import_health_fasting(
    user_id: int, health_fasting: health_fasting_schema.HealthFastingImport, db: Session
) -> bool:
    """Stage an imported fasting session unless the user already has it.

    A session counts as already there when the user has one that started at the same time. A session is
    also skipped when its times are invalid or overlap another session, and a running fast when the user
    already has one running, since only one may run at a time.

    Args:
        user_id: The session's owner.
        health_fasting: The session to import.
        db: Database session.

    Returns:
        True when the session was staged, False when it was skipped.
    """
    start, end = health_fasting.fast_start_time, health_fasting.fast_end_time
    if health_fasting_crud.health_fasting_exists_at(user_id, start, db):
        return False
    try:
        _check_times(start, end, health_fasting.status)
    except core_exceptions.InvalidInputError:
        return False
    if _overlaps(user_id, start, end, health_fasting.status, db):
        return False
    try:
        with db.begin_nested():
            health_fasting_crud.create_health_fasting(
                user_id, health_fasting, db, actual_duration_seconds=_duration_seconds(start, end)
            )
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
        InvalidInputError: If the changed record ends before it started, is completed or broken without an end, or
            is in progress with an end.
        ConflictError: If the changed record overlaps another session or would leave two running.
        PreconditionFailedError: If the record changed since the client read it.
    """

    def stage() -> health_fasting_schema.HealthFastingRead:
        merged = get_health_fasting(user_id, health_fasting_id, db).model_copy(
            update=health_fasting.model_dump(exclude_unset=True)
        )
        _check_times(merged.fast_start_time, merged.fast_end_time, merged.status)
        if _overlaps(
            user_id, merged.fast_start_time, merged.fast_end_time, merged.status, db, exclude_id=health_fasting_id
        ):
            raise core_exceptions.ConflictError(_OVERLAP_MESSAGE)
        return health_fasting_crud.edit_health_fasting(
            user_id,
            health_fasting_id,
            health_fasting,
            db,
            actual_duration_seconds=_duration_seconds(merged.fast_start_time, merged.fast_end_time),
            if_match=if_match,
        )

    return health_record_service.commit_write(
        health_fasting_crud.SPEC,
        health_fasting_id,
        user_id,
        stage,
        db,
        log_message="Edited a fasting session",
    )


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
            _seconds_between(start_time, end_time),
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


def restore_profile_records(
    records: list[dict[str, Any]], user_id: int, ids: users_profile_contracts.ProfileIdMaps, db: Session
) -> int:
    """Stage the fasting records of a profile archive for a user.

    Args:
        records: The archived rows.
        user_id: The importing user.
        ids: The ids restored by earlier sections; the fasting records read none.
        db: Database session.

    Returns:
        The number of records staged.
    """
    return health_record_service.restore_archived_records(
        records,
        health_fasting_schema.HealthFastingImport,
        stage_import_health_fasting,
        user_id,
        db,
        kind="health_fasting",
        server_derived=_SERVER_DERIVED,
    )
