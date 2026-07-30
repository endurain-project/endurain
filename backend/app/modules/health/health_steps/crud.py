from typing import overload

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.health.constants as health_constants
import modules.health.health_steps.models as health_steps_models
import modules.health.health_steps.schema as health_steps_schema
import modules.health.utils as health_utils

# Private internal helpers


@overload
def _transform_health_steps(health_steps: health_steps_models.HealthSteps) -> health_steps_schema.HealthStepsRead: ...


@overload
def _transform_health_steps(
    health_steps: list[health_steps_models.HealthSteps],
) -> list[health_steps_schema.HealthStepsRead]: ...


def _transform_health_steps(
    health_steps: health_steps_models.HealthSteps | list[health_steps_models.HealthSteps],
) -> health_steps_schema.HealthStepsRead | list[health_steps_schema.HealthStepsRead]:
    """
    Transform a health steps or list of health steps to a Pydantic schema.

    Args:
        health_steps: The health steps ORM instance or list of instances.

    Returns:
        The health steps(s) as a schema.
    """
    if isinstance(health_steps, list):
        return [health_steps_schema.HealthStepsRead.model_validate(hw) for hw in health_steps]
    return health_steps_schema.HealthStepsRead.model_validate(health_steps)


@core_decorators.handle_db_errors
def _get_health_steps_model_by_id_and_user_id_or_404(
    health_steps_id: int, user_id: int, db: Session
) -> health_steps_models.HealthSteps:
    """
    Retrieve health steps record model by ID and user ID.

    Args:
        health_steps_id: Health steps record ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        Mapped ``HealthSteps`` ORM instance.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_steps from the database
    stmt = select(health_steps_models.HealthSteps).where(
        health_steps_models.HealthSteps.id == health_steps_id,
        health_steps_models.HealthSteps.user_id == user_id,
    )
    db_health_steps = db.execute(stmt).scalar_one_or_none()

    if db_health_steps is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health steps not found",
        )

    return db_health_steps


# Public CRUD functions


@core_decorators.handle_db_errors
def get_health_steps_number_by_user_id(
    user_id: int, db: Session, interval: health_constants.Interval | None = None
) -> int:
    """
    Retrieve total count of health steps records for a user. If interval is
    provided, count only records starting from the calculated start date.

    Args:
        user_id: User ID to count records for.
        db: Database session.
        interval: Optional filter by goal interval.

    Returns:
        Total number of health steps records.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the number of health_steps from the database
    stmt = (
        select(func.count())
        .select_from(health_steps_models.HealthSteps)
        .where(health_steps_models.HealthSteps.user_id == user_id)
    )

    if interval is not None:
        stmt = stmt.where(
            health_steps_models.HealthSteps.date >= health_utils.get_start_date_for_interval(interval.value)
        )

    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_health_steps_by_user_id(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    interval: health_constants.Interval | None = None,
) -> list[health_steps_schema.HealthStepsRead]:
    """
    Retrieve health steps records for a specific user with optional pagination
        and filtering.

    Args:
        user_id (int): The ID of the user whose health steps records are to be
            retrieved.
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
        list[health_steps_schema.HealthStepsRead]: A list of health steps
            records sorted by date in descending order, optionally paginated.
    """
    # Get the health_steps from the database
    stmt = select(health_steps_models.HealthSteps).where(health_steps_models.HealthSteps.user_id == user_id)

    if interval is not None:
        stmt = stmt.where(
            health_steps_models.HealthSteps.date >= health_utils.get_start_date_for_interval(interval.value)
        )

    stmt = stmt.order_by(desc(health_steps_models.HealthSteps.date))

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    db_health_steps_list = db.execute(stmt).scalars().all()
    return _transform_health_steps(list(db_health_steps_list))


@core_decorators.handle_db_errors
def get_health_steps_by_date_and_user_id(
    user_id: int, date: str, db: Session
) -> health_steps_schema.HealthStepsRead | None:
    """
    Retrieve health steps record for a user on a specific date.

    Args:
        user_id: User ID.
        date: Date string for the steps record.
        db: Database session.

    Returns:
        HealthStepsRead schema if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_steps from the database
    stmt = select(health_steps_models.HealthSteps).where(
        health_steps_models.HealthSteps.date == func.date(date),
        health_steps_models.HealthSteps.user_id == user_id,
    )
    db_health_steps = db.execute(stmt).scalar_one_or_none()
    return _transform_health_steps(db_health_steps) if db_health_steps else None


@core_decorators.handle_db_errors
def create_health_steps(
    user_id: int,
    health_steps: health_steps_schema.HealthStepsCreate,
    db: Session,
) -> health_steps_schema.HealthStepsRead:
    """
    Create a new health steps record for a user.

    Args:
        user_id: User ID for the record owner.
        health_steps: Health steps data to create.
        db: Database session.

    Returns:
        Created health steps record.

    Raises:
        HTTPException: If duplicate entry or database error.
    """
    try:
        # Create a new health_steps
        db_health_steps = health_steps_models.HealthSteps(
            **health_steps.model_dump(exclude_none=False),
            user_id=user_id,
        )

        # Add the health_steps to the database
        db.add(db_health_steps)
        db.commit()
        db.refresh(db_health_steps)

        # Return the health_steps
        return _transform_health_steps(db_health_steps)
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"Duplicate entry error. Check if there is already a entry created for {health_steps.date}"),
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_health_steps(
    user_id: int,
    health_steps: health_steps_schema.HealthStepsUpdate,
    db: Session,
) -> health_steps_schema.HealthStepsRead:
    """
    Edit health steps record for a user.

    Args:
        user_id: User ID who owns the record.
        health_steps: Health steps data to update.
        db: Database session.

    Returns:
        Updated HealthStepsRead schema.

    Raises:
        HTTPException: 403 if trying to edit other user record, 404 if not
            found, 500 if database error.
    """
    # Ensure the health_steps belongs to the user
    if health_steps.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit health steps for another user.",
        )

    # Get the health_steps from the database
    db_health_steps = _get_health_steps_model_by_id_and_user_id_or_404(health_steps.id, user_id, db)

    # Dictionary of the fields to update if they are not None
    health_steps_data = health_steps.model_dump(exclude_unset=True)
    # Iterate over the fields and update the db_health_steps dynamically
    for key, value in health_steps_data.items():
        setattr(db_health_steps, key, value)

    # Commit the transaction
    db.commit()
    # Refresh the object to ensure it reflects database state
    db.refresh(db_health_steps)

    return _transform_health_steps(db_health_steps)


@core_decorators.handle_db_errors
def delete_health_steps(user_id: int, health_steps_id: int, db: Session) -> None:
    """
    Delete a health steps record for a user.

    Args:
        user_id: User ID who owns the record.
        health_steps_id: Health steps record ID to delete.
        db: Database session.

    Returns:
        None

    Raises:
        HTTPException: If record not found or database error.
    """
    # Get the record first to ensure it exists
    db_health_steps = _get_health_steps_model_by_id_and_user_id_or_404(health_steps_id, user_id, db)

    # Delete the health_steps
    db.delete(db_health_steps)
    # Commit the transaction
    db.commit()
