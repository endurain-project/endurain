"""CRUD operations for health fasting records."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.health.computation as health_computation
import modules.health.health_fasting.models as health_fasting_models
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.serializers as health_fasting_serializers

_IN_PROGRESS = health_fasting_schema.FastingStatus.IN_PROGRESS.value
_COMPLETED = health_fasting_schema.FastingStatus.COMPLETED.value


def _get_model_by_id_and_user_id(
    health_fasting_id: int, user_id: int, db: Session
) -> health_fasting_models.HealthFasting:
    """Load a user's fasting row by id.

    Args:
        health_fasting_id: The record to load.
        user_id: The record's owner.
        db: Database session.

    Returns:
        The ORM row.

    Raises:
        NotFoundError: If the user has no such record.
    """
    stmt = select(health_fasting_models.HealthFasting).where(
        health_fasting_models.HealthFasting.id == health_fasting_id,
        health_fasting_models.HealthFasting.user_id == user_id,
    )
    db_health_fasting = db.execute(stmt).scalar_one_or_none()

    if db_health_fasting is None:
        raise core_exceptions.NotFoundError("Health fasting not found")

    return db_health_fasting


def get_health_fasting_number_by_user_id(user_id: int, db: Session, since: date | None = None) -> int:
    """Count a user's fasting records.

    Args:
        user_id: The records' owner.
        db: Database session.
        since: Count only records started on or after this date.

    Returns:
        The number of records.
    """
    stmt = (
        select(func.count())
        .select_from(health_fasting_models.HealthFasting)
        .where(health_fasting_models.HealthFasting.user_id == user_id)
    )
    if since is not None:
        stmt = stmt.where(health_fasting_models.HealthFasting.fast_start_time >= since)

    return db.execute(stmt).scalar_one()


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
    stmt = select(health_fasting_models.HealthFasting).where(
        health_fasting_models.HealthFasting.id == health_fasting_id,
        health_fasting_models.HealthFasting.user_id == user_id,
    )
    db_health_fasting = db.execute(stmt).scalar_one_or_none()

    return health_fasting_serializers.to_read_schema(db_health_fasting) if db_health_fasting else None


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
    stmt = select(health_fasting_models.HealthFasting).where(health_fasting_models.HealthFasting.user_id == user_id)

    if since is not None:
        stmt = stmt.where(health_fasting_models.HealthFasting.fast_start_time >= since)

    stmt = stmt.order_by(desc(health_fasting_models.HealthFasting.fast_start_time))

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    return health_fasting_serializers.to_read_schemas(list(db.execute(stmt).scalars().all()))


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

    return health_fasting_serializers.to_read_schema(db_health_fasting) if db_health_fasting else None


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
        ConflictError: If the insert violates a database constraint.
    """
    db_health_fasting = health_fasting_models.HealthFasting(
        **health_fasting.model_dump(exclude_none=False),
        user_id=user_id,
    )

    try:
        db.add(db_health_fasting)
        db.flush()
        db.refresh(db_health_fasting)
    except IntegrityError as err:
        raise core_exceptions.ConflictError("Failed to create fasting record. Database integrity error.") from err

    return health_fasting_serializers.to_read_schema(db_health_fasting)


def edit_health_fasting(
    user_id: int, health_fasting: health_fasting_schema.HealthFastingUpdate, db: Session
) -> health_fasting_schema.HealthFastingRead:
    """Stage an update to a user's fasting record.

    Args:
        user_id: The record's owner.
        health_fasting: The record with its changes.
        db: Database session.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db_health_fasting = _get_model_by_id_and_user_id(health_fasting.id, user_id, db)

    for key, value in health_fasting.model_dump(exclude_unset=True).items():
        setattr(db_health_fasting, key, value)

    db.flush()
    db.refresh(db_health_fasting)

    return health_fasting_serializers.to_read_schema(db_health_fasting)


def end_health_fasting(
    user_id: int,
    health_fasting_id: int,
    fast_end_time: datetime,
    status: str,
    actual_duration_seconds: int,
    notes: str | None,
    db: Session,
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

    Returns:
        The ended session.

    Raises:
        NotFoundError: If the user has no such session.
    """
    db_health_fasting = _get_model_by_id_and_user_id(health_fasting_id, user_id, db)

    db_health_fasting.fast_end_time = fast_end_time
    db_health_fasting.status = status
    db_health_fasting.actual_duration_seconds = actual_duration_seconds
    if notes:
        db_health_fasting.notes = notes

    db.flush()
    db.refresh(db_health_fasting)

    return health_fasting_serializers.to_read_schema(db_health_fasting)


def delete_health_fasting(user_id: int, health_fasting_id: int, db: Session) -> None:
    """Stage the deletion of a user's fasting record.

    Args:
        user_id: The record's owner.
        health_fasting_id: The record to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such record.
    """
    db.delete(_get_model_by_id_and_user_id(health_fasting_id, user_id, db))
    db.flush()
