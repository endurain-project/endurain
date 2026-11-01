"""CRUD operations for health fasting records."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

import core.etag as core_etag
import modules.health.computation as health_computation
import modules.health.health_fasting.models as health_fasting_models
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.record_crud as health_record_crud

SPEC = health_record_crud.RecordSpec(
    model=health_fasting_models.HealthFasting,
    read_schema=health_fasting_schema.HealthFastingRead,
    not_found="Health fasting not found",
    etag_label="fasting session record",
)
_ACTIVE_FAST_MESSAGE = "User already has an active fasting session"

_IN_PROGRESS = health_fasting_schema.FastingStatus.IN_PROGRESS.value
_COMPLETED = health_fasting_schema.FastingStatus.COMPLETED.value


def get_health_fasting_number_by_user_id(user_id: int, db: Session, since: date | None = None) -> int:
    """Count a user's fasting records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records started on or after this date.

    Returns:
        The number of records.
    """
    return health_record_crud.count(SPEC, user_id, health_fasting_models.HealthFasting.fast_start_time, since, db)


def get_health_fasting_by_id_and_user_id(
    health_fasting_id: int, user_id: int, db: Session
) -> health_fasting_schema.HealthFastingRead | None:
    """Retrieve a user's fasting record by id.

    Args:
        health_fasting_id: The record to fetch.
        user_id: The record's owner.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    return health_record_crud.find_by_id(SPEC, health_fasting_id, user_id, db)


def get_health_fasting_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    since: date | None = None,
) -> list[health_fasting_schema.HealthFastingRead]:
    """Retrieve a user's fasting records, optionally paginated and bounded.

    Args:
        user_id: The records' owner.
        db: Database session.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        since: Return only records started on or after this date.

    Returns:
        The records ordered by start time descending.
    """
    fast_start_time = health_fasting_models.HealthFasting.fast_start_time
    return health_record_crud.list_page(
        SPEC, user_id, fast_start_time, fast_start_time, since, page_number, num_records, db
    )


def get_active_fasting_by_user_id(user_id: int, db: Session) -> health_fasting_schema.HealthFastingRead | None:
    """Retrieve a user's in-progress fasting session.

    Args:
        user_id: The session's owner.
        db: Database session.

    Returns:
        The active session, or ``None``.
    """
    stmt = (
        select(health_fasting_models.HealthFasting)
        .where(
            health_fasting_models.HealthFasting.user_id == user_id,
            health_fasting_models.HealthFasting.status == _IN_PROGRESS,
        )
        .order_by(desc(health_fasting_models.HealthFasting.fast_start_time))
    )
    db_health_fasting = db.execute(stmt).scalar_one_or_none()

    return (
        health_computation.to_read_schema(health_fasting_schema.HealthFastingRead, db_health_fasting)
        if db_health_fasting
        else None
    )


def get_completed_fasting_count(user_id: int, db: Session) -> int:
    """Count a user's completed fasting sessions.

    Args:
        user_id: The sessions' owner.
        db: Database session.

    Returns:
        The number of completed sessions.
    """
    stmt = (
        select(func.count())
        .select_from(health_fasting_models.HealthFasting)
        .where(
            health_fasting_models.HealthFasting.user_id == user_id,
            health_fasting_models.HealthFasting.status == _COMPLETED,
        )
    )
    return db.execute(stmt).scalar_one()


def get_total_fasting_seconds(user_id: int, db: Session) -> int:
    """Sum the duration of a user's completed fasting sessions.

    Args:
        user_id: The sessions' owner.
        db: Database session.

    Returns:
        The total duration in seconds.
    """
    stmt = (
        select(func.coalesce(func.sum(health_fasting_models.HealthFasting.actual_duration_seconds), 0))
        .select_from(health_fasting_models.HealthFasting)
        .where(
            health_fasting_models.HealthFasting.user_id == user_id,
            health_fasting_models.HealthFasting.status == _COMPLETED,
        )
    )
    return db.execute(stmt).scalar_one() or 0


def get_avg_fasting_duration(user_id: int, db: Session) -> int | None:
    """Average the duration of a user's completed fasting sessions.

    Args:
        user_id: The sessions' owner.
        db: Database session.

    Returns:
        The average duration in seconds, or ``None`` without data.
    """
    stmt = (
        select(func.avg(health_fasting_models.HealthFasting.actual_duration_seconds))
        .select_from(health_fasting_models.HealthFasting)
        .where(
            health_fasting_models.HealthFasting.user_id == user_id,
            health_fasting_models.HealthFasting.status == _COMPLETED,
        )
    )
    result: Decimal | None = db.execute(stmt).scalar_one()
    return int(result) if result else None


def get_completed_fasting_dates_by_user_id(user_id: int, tz_name: str, db: Session) -> list[date]:
    """List the distinct local dates on which a user started a completed fast.

    Selects only the date component so a streak calculation does not have to
    materialize full records.

    Args:
        user_id: The sessions' owner.
        tz_name: IANA timezone the dates are bucketed in.
        db: Database session.

    Returns:
        The distinct dates, ascending.
    """
    fast_date = health_computation.local_date_expression(health_fasting_models.HealthFasting.fast_start_time, tz_name)
    stmt = (
        select(fast_date)
        .where(
            health_fasting_models.HealthFasting.user_id == user_id,
            health_fasting_models.HealthFasting.status == _COMPLETED,
        )
        .distinct()
        .order_by(fast_date)
    )
    return list(db.execute(stmt).scalars().all())


def health_fasting_exists_at(user_id: int, fast_start_time: datetime, db: Session) -> bool:
    """Tell whether a user already has a fasting session started at an exact time.

    Args:
        user_id: The session's owner.
        fast_start_time: The session's start time.
        db: Database session.

    Returns:
        True when the user has a session that started at that time.
    """
    stmt = select(
        select(health_fasting_models.HealthFasting.id)
        .where(
            health_fasting_models.HealthFasting.user_id == user_id,
            health_fasting_models.HealthFasting.fast_start_time == fast_start_time,
        )
        .exists()
    )
    return bool(db.execute(stmt).scalar())


def create_health_fasting(
    user_id: int, health_fasting: health_fasting_schema.HealthFastingCreate, db: Session
) -> health_fasting_schema.HealthFastingRead:
    """Stage a new fasting session for a user.

    Args:
        user_id: The session's owner.
        health_fasting: The session to create.
        db: Database session.

    Returns:
        The staged session.

    Raises:
        ConflictError: If the user already has a running fast.
    """
    return health_record_crud.create(SPEC, user_id, health_fasting, db, conflict=_ACTIVE_FAST_MESSAGE)


def edit_health_fasting(
    user_id: int,
    health_fasting_id: int,
    health_fasting: health_fasting_schema.HealthFastingUpdate,
    db: Session,
    *,
    if_match: str,
) -> health_fasting_schema.HealthFastingRead:
    """Stage an update to a user's fasting record.

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
        PreconditionFailedError: When ``if_match`` does not name the row's version.
        ConflictError: If the change would leave the user with two running fasts.
    """
    return health_record_crud.edit(
        SPEC, health_fasting_id, user_id, health_fasting, db, if_match=if_match, conflict=_ACTIVE_FAST_MESSAGE
    )


def end_health_fasting(
    user_id: int,
    health_fasting_id: int,
    fast_end_time: datetime,
    status: str,
    actual_duration_seconds: int,
    notes: str | None,
    db: Session,
    *,
    if_match: str,
) -> health_fasting_schema.HealthFastingRead:
    """Stage the end of a user's fasting session.

    Args:
        user_id: The session's owner.
        health_fasting_id: The session to end.
        fast_end_time: When the fast ended.
        status: The session's final status.
        actual_duration_seconds: How long the fast lasted.
        notes: Notes to store; left as they are when empty.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The ended session.

    Raises:
        NotFoundError: If the user has no such session.
        PreconditionFailedError: When ``if_match`` does not name the session's version.
    """
    db_health_fasting = health_record_crud.get_owned(SPEC, health_fasting_id, user_id, db)
    core_etag.require_if_match(if_match, db_health_fasting.version, SPEC.etag_label)

    db_health_fasting.fast_end_time = fast_end_time
    db_health_fasting.status = status
    db_health_fasting.actual_duration_seconds = actual_duration_seconds
    if notes:
        db_health_fasting.notes = notes

    return health_record_crud.save(SPEC, db_health_fasting, db)


def delete_health_fasting(user_id: int, health_fasting_id: int, db: Session, *, if_match: str) -> None:
    """Stage the deletion of a user's fasting record.

    Args:
        user_id: The record's owner.
        health_fasting_id: The record to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    health_record_crud.delete(SPEC, health_fasting_id, user_id, db, if_match=if_match)
