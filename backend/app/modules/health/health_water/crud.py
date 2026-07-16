"""
CRUD operations for health water intake records.

This module provides database operations for creating, reading,
updating, and deleting water intake records.
"""

from typing import overload

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.health.constants as health_constants
import modules.health.health_water.models as health_water_models
import modules.health.health_water.schema as health_water_schema
import modules.health.utils as health_utils

# Private internal helpers


@overload
def _transform_health_water(health_water: health_water_models.HealthWater) -> health_water_schema.HealthWaterRead: ...


@overload
def _transform_health_water(
    health_water: list[health_water_models.HealthWater],
) -> list[health_water_schema.HealthWaterRead]: ...


def _transform_health_water(
    health_water: health_water_models.HealthWater | list[health_water_models.HealthWater],
) -> health_water_schema.HealthWaterRead | list[health_water_schema.HealthWaterRead]:
    """
    Transform a health water or list of health waters to a Pydantic schema.

    Args:
        health_water: The health water ORM instance or list of instances.

    Returns:
        The health water(s) as a schema.
    """
    if isinstance(health_water, list):
        return [health_water_schema.HealthWaterRead.model_validate(hw) for hw in health_water]
    return health_water_schema.HealthWaterRead.model_validate(health_water)


@core_decorators.handle_db_errors
def _get_health_water_model_by_id_and_user_id_or_404(
    health_water_id: int, user_id: int, db: Session
) -> health_water_models.HealthWater:
    """
    Retrieve health water record model by ID and user ID.

    Args:
        health_water_id: Health water record ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        Mapped ``HealthWater`` ORM instance.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_water from the database
    stmt = select(health_water_models.HealthWater).where(
        health_water_models.HealthWater.id == health_water_id,
        health_water_models.HealthWater.user_id == user_id,
    )
    db_health_water = db.execute(stmt).scalar_one_or_none()

    if db_health_water is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health water not found",
        )

    return db_health_water


# Public CRUD functions


@core_decorators.handle_db_errors
def get_health_water_number_by_user_id(
    user_id: int,
    db: Session,
    interval: health_constants.Interval | None = None,
) -> int:
    """
    Retrieve total count of water intake records for a user.

    If interval is provided, count only records starting from
    the calculated start date.

    Args:
        user_id: User ID to count records for.
        db: Database session.
        interval: Optional filter by goal interval.

    Returns:
        Total number of health water intake records.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(func.count())
        .select_from(health_water_models.HealthWater)
        .where(health_water_models.HealthWater.user_id == user_id)
    )

    if interval is not None:
        stmt = stmt.where(
            health_water_models.HealthWater.date >= health_utils.get_start_date_for_interval(interval.value)
        )

    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_health_water_by_id_and_user_id(
    health_water_id: int, user_id: int, db: Session
) -> health_water_schema.HealthWaterRead | None:
    """
    Retrieve water intake record by ID and user ID.

    Args:
        health_water_id: Water intake record ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        HealthWaterRead schema if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = select(health_water_models.HealthWater).where(
        health_water_models.HealthWater.id == health_water_id,
        health_water_models.HealthWater.user_id == user_id,
    )
    db_health_water = db.execute(stmt).scalar_one_or_none()
    return _transform_health_water(db_health_water) if db_health_water else None


@core_decorators.handle_db_errors
def get_health_water_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    interval: health_constants.Interval | None = None,
) -> list[health_water_schema.HealthWaterRead]:
    """
    Retrieve water intake records for a user with optional
    pagination and filtering.

    Args:
        user_id: User ID whose records are to be retrieved.
        db: Database session used to execute the query.
        page_number: Page number for pagination (1-indexed).
        num_records: Number of records per page.
        interval: Time interval to filter records.

    Returns:
        List of HealthWaterRead schema records sorted by date descending.
    """
    stmt = select(health_water_models.HealthWater).where(health_water_models.HealthWater.user_id == user_id)

    if interval is not None:
        stmt = stmt.where(
            health_water_models.HealthWater.date >= health_utils.get_start_date_for_interval(interval.value)
        )

    stmt = stmt.order_by(desc(health_water_models.HealthWater.date))

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    db_health_water = db.execute(stmt).scalars().all()

    return _transform_health_water(list(db_health_water))


@core_decorators.handle_db_errors
def get_health_water_by_date_and_user_id(
    user_id: int, date: str, db: Session
) -> health_water_schema.HealthWaterRead | None:
    """
    Retrieve water intake record for a user on a specific date.

    Args:
        user_id: User ID.
        date: Date string for the water intake record.
        db: Database session.

    Returns:
        HealthWaterRead schema if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = select(health_water_models.HealthWater).where(
        health_water_models.HealthWater.date == func.date(date),
        health_water_models.HealthWater.user_id == user_id,
    )
    db_health_water = db.execute(stmt).scalar_one_or_none()

    return _transform_health_water(db_health_water) if db_health_water else None


@core_decorators.handle_db_errors
def create_health_water(
    user_id: int,
    health_water: health_water_schema.HealthWaterCreate,
    db: Session,
) -> health_water_schema.HealthWaterRead:
    """
    Create a new water intake record for a user.

    Args:
        user_id: User ID for the record owner.
        health_water: Water intake data to create.
        db: Database session.

    Returns:
        Created water intake record.

    Raises:
        HTTPException: If duplicate entry or database error.
    """
    try:
        db_health_water = health_water_models.HealthWater(
            **health_water.model_dump(exclude_none=False),
            user_id=user_id,
        )

        db.add(db_health_water)
        db.commit()
        db.refresh(db_health_water)

        return _transform_health_water(db_health_water)
    except IntegrityError as integrity_error:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"Duplicate entry error. Check if there is already an entry created for {health_water.date}"),
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_health_water(
    user_id: int,
    health_water: health_water_schema.HealthWaterUpdate,
    db: Session,
) -> health_water_schema.HealthWaterRead:
    """
    Edit water intake record for a user.

    Args:
        user_id: User ID who owns the record.
        health_water: Water intake data to update.
        db: Database session.

    Returns:
        Updated HealthWaterRead schema.

    Raises:
        HTTPException: 403 if editing another user's record,
            404 if not found, 500 if database error.
    """
    if health_water.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("Cannot edit health water intake for another user."),
        )

    db_health_water = _get_health_water_model_by_id_and_user_id_or_404(health_water.id, user_id, db)

    health_water_data = health_water.model_dump(exclude_unset=True)
    for key, value in health_water_data.items():
        setattr(db_health_water, key, value)

    db.commit()
    db.refresh(db_health_water)

    return _transform_health_water(db_health_water)


@core_decorators.handle_db_errors
def delete_health_water(user_id: int, health_water_id: int, db: Session) -> None:
    """
    Delete a water intake record for a user.

    Args:
        user_id: User ID who owns the record.
        health_water_id: Water intake record ID to delete.
        db: Database session.

    Returns:
        None

    Raises:
        HTTPException: If record not found or database error.
    """
    db_health_water = _get_health_water_model_by_id_and_user_id_or_404(health_water_id, user_id, db)

    db.delete(db_health_water)
    db.commit()
