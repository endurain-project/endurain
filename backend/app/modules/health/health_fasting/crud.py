"""
CRUD operations for health fasting records.

This module provides database operations for creating, reading, updating,
and deleting fasting session records.
"""

from datetime import date
from decimal import Decimal
from typing import overload

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.timezone as core_timezone
import modules.health.constants as health_constants
import modules.health.health_fasting.models as health_fasting_models
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.utils as health_utils
import modules.users.users.utils as users_utils

# Private internal helpers


@overload
def _transform_health_fasting(
    health_fasting: health_fasting_models.HealthFasting,
) -> health_fasting_schema.HealthFastingRead: ...


@overload
def _transform_health_fasting(
    health_fasting: list[health_fasting_models.HealthFasting],
) -> list[health_fasting_schema.HealthFastingRead]: ...


def _transform_health_fasting(
    health_fasting: health_fasting_models.HealthFasting | list[health_fasting_models.HealthFasting],
) -> health_fasting_schema.HealthFastingRead | list[health_fasting_schema.HealthFastingRead]:
    """
    Transform a health fasting or list of health fasting to a Pydantic schema.

    Args:
        health_poop: The health poop ORM instance or list of instances.

    Returns:
        The health fasting(s) as a schema.
    """
    if isinstance(health_fasting, list):
        return [health_fasting_schema.HealthFastingRead.model_validate(hw) for hw in health_fasting]
    return health_fasting_schema.HealthFastingRead.model_validate(health_fasting)


@core_decorators.handle_db_errors
def _get_health_fasting_model_by_id_and_user_id_or_404(
    health_fasting_id: int, user_id: int, db: Session
) -> health_fasting_models.HealthFasting:
    """
    Retrieve health fasting record model by ID and user ID.

    Args:
        health_fasting_id: Health fasting record ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        Mapped ``HealthFasting`` ORM instance.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_fasting from the database
    stmt = select(health_fasting_models.HealthFasting).where(
        health_fasting_models.HealthFasting.id == health_fasting_id,
        health_fasting_models.HealthFasting.user_id == user_id,
    )
    db_health_fasting = db.execute(stmt).scalar_one_or_none()

    if db_health_fasting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health fasting not found",
        )

    return db_health_fasting


# Public CRUD functions


@core_decorators.handle_db_errors
def get_health_fasting_number_by_user_id(
    user_id: int, db: Session, interval: health_constants.Interval | None = None
) -> int:
    """
    Retrieve total count of health fasting records for a user. If interval is
    provided, count only records starting from the calculated start date.

    Args:
        user_id: User ID to count records for.
        db: Database session.
        interval: Optional filter by goal interval.

    Returns:
        Total number of health fasting records.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(func.count())
        .select_from(health_fasting_models.HealthFasting)
        .where(health_fasting_models.HealthFasting.user_id == user_id)
    )

    if interval is not None:
        stmt = stmt.where(
            health_fasting_models.HealthFasting.fast_start_time
            >= health_utils.get_start_date_for_interval(interval.value, users_utils.user_local_today(user_id, db))
        )

    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_health_fasting_by_id_and_user_id(
    health_fasting_id: int, user_id: int, db: Session
) -> health_fasting_schema.HealthFastingRead | None:
    """
    Retrieve fasting record by ID and user ID.

    Args:
        health_fasting_id: Fasting record ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        HealthFasting schema if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = select(health_fasting_models.HealthFasting).where(
        health_fasting_models.HealthFasting.id == health_fasting_id,
        health_fasting_models.HealthFasting.user_id == user_id,
    )
    db_health_fasting = db.execute(stmt).scalar_one_or_none()
    return _transform_health_fasting(db_health_fasting) if db_health_fasting else None


@core_decorators.handle_db_errors
def get_health_fasting_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    interval: health_constants.Interval | None = None,
) -> list[health_fasting_schema.HealthFastingRead]:
    """
    Retrieve health fasting records for a specific user with optional
        pagination and filtering.

    Args:
        user_id (int): The ID of the user whose health fasting records are to
            be retrieved.
        db (Session): The database session used to execute the query.
        page_number (int | None, optional): The page number for pagination
            (1-indexed).
            If provided, num_records must also be provided. Defaults to None.
        num_records (int | None, optional): The number of records per page.
            If provided, page_number must also be provided. Defaults to None.
        interval (health_constants.Interval | None, optional): The time
            interval to filter records.
            If provided, only records from the start of the interval to present
            are returned. Defaults to None.

    Returns:
        list[health_fasting_schema.HealthFastingRead]: A list of health fasting
            records sorted by fast_start_time in descending order, optionally
            paginated.
    """
    # Get the health_fasting from the database
    stmt = select(health_fasting_models.HealthFasting).where(health_fasting_models.HealthFasting.user_id == user_id)

    if interval is not None:
        stmt = stmt.where(
            health_fasting_models.HealthFasting.fast_start_time
            >= health_utils.get_start_date_for_interval(interval.value, users_utils.user_local_today(user_id, db))
        )

    stmt = stmt.order_by(desc(health_fasting_models.HealthFasting.fast_start_time))
    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    db_health_fastings = db.execute(stmt).scalars().all()
    return _transform_health_fasting(list(db_health_fastings))


@core_decorators.handle_db_errors
def get_active_fasting_by_user_id(user_id: int, db: Session) -> health_fasting_schema.HealthFastingRead | None:
    """
    Retrieve the active (in_progress) fasting session for a user.

    Args:
        user_id: User ID to fetch active fast for.
        db: Database session.

    Returns:
        HealthFastingRead schema if active fast exists, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(health_fasting_models.HealthFasting)
        .where(
            health_fasting_models.HealthFasting.user_id == user_id,
            health_fasting_models.HealthFasting.status == "in_progress",
        )
        .order_by(desc(health_fasting_models.HealthFasting.fast_start_time))
    )
    db_health_fasting = db.execute(stmt).scalar_one_or_none()
    return _transform_health_fasting(db_health_fasting) if db_health_fasting else None


@core_decorators.handle_db_errors
def get_completed_fasting_count(user_id: int, db: Session) -> int:
    """
    Get the count of completed fasting sessions for a user.

    Args:
        user_id: User ID to count completed fasts for.
        db: Database session.

    Returns:
        Number of completed fasting sessions.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(func.count())
        .select_from(health_fasting_models.HealthFasting)
        .where(
            health_fasting_models.HealthFasting.user_id == user_id,
            health_fasting_models.HealthFasting.status == "completed",
        )
    )
    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_total_fasting_seconds(user_id: int, db: Session) -> int:
    """
    Get total fasting duration in seconds for a user.

    Args:
        user_id: User ID to calculate total for.
        db: Database session.

    Returns:
        Total fasting duration in seconds.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(func.coalesce(func.sum(health_fasting_models.HealthFasting.actual_duration_seconds), 0))
        .select_from(health_fasting_models.HealthFasting)
        .where(
            health_fasting_models.HealthFasting.user_id == user_id,
            health_fasting_models.HealthFasting.status == "completed",
        )
    )
    return db.execute(stmt).scalar_one() or 0


@core_decorators.handle_db_errors
def get_avg_fasting_duration(user_id: int, db: Session) -> int | None:
    """
    Get average fasting duration in seconds for a user.

    Args:
        user_id: User ID to calculate average for.
        db: Database session.

    Returns:
        Average fasting duration in seconds, None if no data.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(func.avg(health_fasting_models.HealthFasting.actual_duration_seconds))
        .select_from(health_fasting_models.HealthFasting)
        .where(
            health_fasting_models.HealthFasting.user_id == user_id,
            health_fasting_models.HealthFasting.status == "completed",
        )
    )
    result: Decimal | None = db.execute(stmt).scalar_one()
    return int(result) if result else None


@core_decorators.handle_db_errors
def get_completed_fasting_dates_by_user_id(user_id: int, db: Session) -> list[date]:
    """
    Get the distinct dates a user completed a fast, sorted ascending.

    Selects only the date component directly from the database so the
    streak calculation does not have to materialize full records.

    Args:
        user_id: User ID to fetch completed fasting dates for.
        db: Database session.

    Returns:
        Sorted list of distinct dates with a completed fast.

    Raises:
        HTTPException: If database error occurs.
    """
    fast_date = health_utils.local_date_expression(
        health_fasting_models.HealthFasting.fast_start_time,
        users_utils.resolve_user_timezone(user_id, db),
        db,
    )
    stmt = (
        select(fast_date)
        .where(
            health_fasting_models.HealthFasting.user_id == user_id,
            health_fasting_models.HealthFasting.status == "completed",
        )
        .distinct()
        .order_by(fast_date)
    )
    return list(db.execute(stmt).scalars().all())


@core_decorators.handle_db_errors
def create_health_fasting(
    user_id: int,
    health_fasting: health_fasting_schema.HealthFastingCreate,
    db: Session,
) -> health_fasting_schema.HealthFastingRead:
    """
    Create a new fasting session for a user.

    Args:
        user_id: User ID to create the fasting session for.
        health_fasting: Fasting data to create.
        db: Database session.

    Returns:
        Created HealthFastingRead schema.

    Raises:
        HTTPException: If database error or duplicate entry.
    """
    try:
        db_health_fasting = health_fasting_models.HealthFasting(
            **health_fasting.model_dump(exclude_none=False),
            user_id=user_id,
        )

        db.add(db_health_fasting)
        db.commit()
        db.refresh(db_health_fasting)

        return _transform_health_fasting(db_health_fasting)
    except IntegrityError as integrity_error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Failed to create fasting record. Database integrity error.",
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_health_fasting(
    user_id: int,
    health_fasting: health_fasting_schema.HealthFastingUpdate,
    db: Session,
) -> health_fasting_schema.HealthFastingRead:
    """
    Edit an existing fasting record for a user.

    Args:
        user_id: User ID who owns the fasting record.
        health_fasting: Fasting data to update.
        db: Database session.

    Returns:
        Updated HealthFasting model.

    Raises:
        HTTPException: If record not found or permission denied.
    """
    if health_fasting.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit fasting record for another user.",
        )

    db_health_fasting = _get_health_fasting_model_by_id_and_user_id_or_404(health_fasting.id, user_id, db)

    health_fasting_data = health_fasting.model_dump(exclude_unset=True)
    for key, value in health_fasting_data.items():
        setattr(db_health_fasting, key, value)

    db.commit()
    db.refresh(db_health_fasting)

    return _transform_health_fasting(db_health_fasting)


@core_decorators.handle_db_errors
def complete_health_fasting(
    user_id: int,
    health_fasting_id: int,
    complete_data: health_fasting_schema.HealthFastingComplete,
    db: Session,
) -> health_fasting_schema.HealthFastingRead:
    """
    Complete or end a fasting session.

    Args:
        user_id: User ID who owns the fasting record.
        health_fasting_id: ID of the fasting record to complete.
        complete_data: Completion data including end time and status.
        db: Database session.

    Returns:
        Updated HealthFasting model.

    Raises:
        HTTPException: If record not found or not in progress.
    """
    db_health_fasting = _get_health_fasting_model_by_id_and_user_id_or_404(health_fasting_id, user_id, db)

    if db_health_fasting.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fasting session is not in progress",
        )

    # Calculate actual duration. Normalize the client-supplied end time to
    # aware UTC first: a payload without an offset yields a naive datetime, and
    # subtracting it from the aware value loaded from the timestamptz column
    # raises TypeError — which ``handle_db_errors`` does not catch, so it
    # surfaced as an unhandled 500.
    start_time = core_timezone.to_utc_aware(db_health_fasting.fast_start_time)
    end_time = core_timezone.to_utc_aware(complete_data.fast_end_time)

    # Calculate actual_duration in seconds
    actual_duration = int((end_time - start_time).total_seconds())

    # Update the record
    db_health_fasting.fast_end_time = end_time
    db_health_fasting.status = complete_data.status.value
    db_health_fasting.actual_duration_seconds = actual_duration
    if complete_data.notes:
        db_health_fasting.notes = complete_data.notes

    db.commit()
    db.refresh(db_health_fasting)

    return _transform_health_fasting(db_health_fasting)


@core_decorators.handle_db_errors
def delete_health_fasting(user_id: int, health_fasting_id: int, db: Session) -> None:
    """
    Delete a fasting record for a user.

    Args:
        user_id: User ID who owns the fasting record.
        health_fasting_id: Fasting record ID to delete.
        db: Database session.

    Returns:
        None

    Raises:
        HTTPException: If record not found.
    """
    db_health_fasting = _get_health_fasting_model_by_id_and_user_id_or_404(health_fasting_id, user_id, db)

    db.delete(db_health_fasting)
    db.commit()
