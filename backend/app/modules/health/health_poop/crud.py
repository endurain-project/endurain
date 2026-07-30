"""
CRUD operations for health poop (bowel movement) records.

This module provides database operations for creating, reading,
updating, and deleting bowel movement records.
"""

from typing import overload

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.health.constants as health_constants
import modules.health.health_poop.models as health_poop_models
import modules.health.health_poop.schema as health_poop_schema
import modules.health.utils as health_utils

# Private internal helpers


@overload
def _transform_health_poop(health_poop: health_poop_models.HealthPoop) -> health_poop_schema.HealthPoopRead: ...


@overload
def _transform_health_poop(
    health_poop: list[health_poop_models.HealthPoop],
) -> list[health_poop_schema.HealthPoopRead]: ...


def _transform_health_poop(
    health_poop: health_poop_models.HealthPoop | list[health_poop_models.HealthPoop],
) -> health_poop_schema.HealthPoopRead | list[health_poop_schema.HealthPoopRead]:
    """
    Transform a health poop or list of health poop to a Pydantic schema.

    Args:
        health_poop: The health poop ORM instance or list of instances.

    Returns:
        The health poop(s) as a schema.
    """
    if isinstance(health_poop, list):
        return [health_poop_schema.HealthPoopRead.model_validate(hw) for hw in health_poop]
    return health_poop_schema.HealthPoopRead.model_validate(health_poop)


@core_decorators.handle_db_errors
def _get_health_poop_model_by_id_and_user_id_or_404(
    health_poop_id: int, user_id: int, db: Session
) -> health_poop_models.HealthPoop:
    """
    Retrieve health poop record model by ID and user ID.

    Args:
        health_poop_id: Health poop record ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        Mapped ``HealthPoop`` ORM instance.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_poop from the database
    stmt = select(health_poop_models.HealthPoop).where(
        health_poop_models.HealthPoop.id == health_poop_id,
        health_poop_models.HealthPoop.user_id == user_id,
    )
    db_health_poop = db.execute(stmt).scalar_one_or_none()

    if db_health_poop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health poop not found",
        )

    return db_health_poop


# Public CRUD functions


@core_decorators.handle_db_errors
def get_health_poop_number_by_user_id(
    user_id: int,
    db: Session,
    interval: health_constants.Interval | None = None,
) -> int:
    """
    Retrieve total count of poop records for a user.

    If interval is provided, count only records starting from
    the calculated start date.

    Args:
        user_id: User ID to count records for.
        db: Database session.
        interval: Optional filter by goal interval.

    Returns:
        Total number of health poop records.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(func.count())
        .select_from(health_poop_models.HealthPoop)
        .where(health_poop_models.HealthPoop.user_id == user_id)
    )

    if interval is not None:
        stmt = stmt.where(
            health_poop_models.HealthPoop.date_time >= health_utils.get_start_date_for_interval(interval.value)
        )

    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_health_poop_by_id_and_user_id(
    health_poop_id: int, user_id: int, db: Session
) -> health_poop_schema.HealthPoopRead | None:
    """
    Retrieve poop record by ID and user ID.

    Args:
        health_poop_id: Poop record ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        HealthPoopRead schema if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = select(health_poop_models.HealthPoop).where(
        health_poop_models.HealthPoop.id == health_poop_id,
        health_poop_models.HealthPoop.user_id == user_id,
    )
    db_health_poop = db.execute(stmt).scalar_one_or_none()

    return _transform_health_poop(db_health_poop) if db_health_poop else None


@core_decorators.handle_db_errors
def get_health_poop_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    interval: health_constants.Interval | None = None,
) -> list[health_poop_schema.HealthPoopRead]:
    """
    Retrieve poop records for a user with optional pagination
    and filtering.

    Args:
        user_id: User ID whose records are to be retrieved.
        db: Database session used to execute the query.
        page_number: Page number for pagination (1-indexed).
        num_records: Number of records per page.
        interval: Time interval to filter records.

    Returns:
        List of HealthPoopRead records sorted by date_time
            descending.
    """
    stmt = select(health_poop_models.HealthPoop).where(health_poop_models.HealthPoop.user_id == user_id)

    if interval is not None:
        stmt = stmt.where(
            health_poop_models.HealthPoop.date_time >= health_utils.get_start_date_for_interval(interval.value)
        )

    stmt = stmt.order_by(desc(health_poop_models.HealthPoop.date_time))

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    db_health_poops = db.execute(stmt).scalars().all()

    return _transform_health_poop(list(db_health_poops))


@core_decorators.handle_db_errors
def get_health_poop_by_date_and_user_id(
    user_id: int, date: str, db: Session
) -> list[health_poop_schema.HealthPoopRead]:
    """
    Retrieve poop records for a user on a specific date.

    Unlike other health modules, poop can have multiple entries
    per day, so this returns a list.

    Args:
        user_id: User ID.
        date: Date string for the poop records.
        db: Database session.

    Returns:
        List of HealthPoopRead schemas for the given date.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(health_poop_models.HealthPoop)
        .where(
            func.date(health_poop_models.HealthPoop.date_time) == func.date(date),
            health_poop_models.HealthPoop.user_id == user_id,
        )
        .order_by(desc(health_poop_models.HealthPoop.date_time))
    )
    db_health_poops = db.execute(stmt).scalars().all()
    return _transform_health_poop(list(db_health_poops))


@core_decorators.handle_db_errors
def create_health_poop(
    user_id: int,
    health_poop: health_poop_schema.HealthPoopCreate,
    db: Session,
) -> health_poop_schema.HealthPoopRead:
    """
    Create a new poop record for a user.

    Args:
        user_id: User ID for the record owner.
        health_poop: Poop data to create.
        db: Database session.

    Returns:
        Created poop record.

    Raises:
        HTTPException: If database integrity error.
    """
    try:
        db_health_poop = health_poop_models.HealthPoop(
            **health_poop.model_dump(exclude_none=False),
            user_id=user_id,
        )

        db.add(db_health_poop)
        db.commit()
        db.refresh(db_health_poop)

        return _transform_health_poop(db_health_poop)
    except IntegrityError as integrity_error:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Failed to create poop record. Database integrity error."),
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_health_poop(
    user_id: int,
    health_poop: health_poop_schema.HealthPoopUpdate,
    db: Session,
) -> health_poop_schema.HealthPoopRead:
    """
    Edit poop record for a user.

    Args:
        user_id: User ID who owns the record.
        health_poop: Poop data to update.
        db: Database session.

    Returns:
        Updated HealthPoopRead schema.

    Raises:
        HTTPException: 403 if editing another user's record,
            404 if not found, 500 if database error.
    """
    if health_poop.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("Cannot edit health poop record for another user."),
        )

    db_health_poop = _get_health_poop_model_by_id_and_user_id_or_404(health_poop.id, user_id, db)

    health_poop_data = health_poop.model_dump(exclude_unset=True)
    for key, value in health_poop_data.items():
        setattr(db_health_poop, key, value)

    db.commit()
    db.refresh(db_health_poop)

    return _transform_health_poop(db_health_poop)


@core_decorators.handle_db_errors
def delete_health_poop(user_id: int, health_poop_id: int, db: Session) -> None:
    """
    Delete a poop record for a user.

    Args:
        user_id: User ID who owns the record.
        health_poop_id: Poop record ID to delete.
        db: Database session.

    Returns:
        None

    Raises:
        HTTPException: If record not found or database error.
    """
    db_health_poop = _get_health_poop_model_by_id_and_user_id_or_404(health_poop_id, user_id, db)

    db.delete(db_health_poop)
    db.commit()
