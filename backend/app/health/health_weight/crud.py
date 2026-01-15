from typing import cast

from fastapi import HTTPException, status
from sqlalchemy import func, desc, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import health.health_weight.schema as health_weight_schema
import health.health_weight.models as health_weight_models
import health.health_weight.utils as health_weight_utils

import core.decorators as core_decorators


@core_decorators.handle_db_errors
def get_all_health_weight(
    db: Session,
) -> list[health_weight_models.HealthWeight]:
    """
    Retrieve all health weight records from the database.

    Args:
        db: Database session.

    Returns:
        List of HealthWeight models ordered by date descending.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_weight from the database
    stmt = select(health_weight_models.HealthWeight).order_by(
        desc(health_weight_models.HealthWeight.date)
    )
    return db.execute(stmt).scalars().all()


@core_decorators.handle_db_errors
def get_health_weight_number(user_id: int, db: Session) -> int:
    """
    Retrieve total count of health weight records for a user.

    Args:
        user_id: User ID to count records for.
        db: Database session.

    Returns:
        Total number of health weight records.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the number of health_weight from the database
    stmt = (
        select(func.count())
        .select_from(health_weight_models.HealthWeight)
        .where(health_weight_models.HealthWeight.user_id == user_id)
    )
    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_all_health_weight_by_user_id(
    user_id: int, db: Session
) -> list[health_weight_models.HealthWeight]:
    """
    Retrieve all health weight records for a user.

    Args:
        user_id: User ID to fetch records for.
        db: Database session.

    Returns:
        List of HealthWeight models ordered by date descending.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_weight from the database
    stmt = (
        select(health_weight_models.HealthWeight)
        .where(health_weight_models.HealthWeight.user_id == user_id)
        .order_by(desc(health_weight_models.HealthWeight.date))
    )
    return db.execute(stmt).scalars().all()


@core_decorators.handle_db_errors
def get_health_weight_by_id_and_user_id(
    health_weight_id: int, user_id: int, db: Session
) -> health_weight_models.HealthWeight | None:
    """
    Retrieve health weight record by ID and user ID.

    Args:
        health_weight_id: Health weight record ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        HealthWeight model if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_weight from the database
    stmt = select(health_weight_models.HealthWeight).where(
        health_weight_models.HealthWeight.id == health_weight_id,
        health_weight_models.HealthWeight.user_id == user_id,
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_health_weight_with_pagination(
    user_id: int,
    db: Session,
    page_number: int = 1,
    num_records: int = 5,
) -> list[health_weight_models.HealthWeight]:
    """
    Retrieve paginated health weight records for a user.

    Args:
        user_id: User ID to fetch records for.
        db: Database session.
        page_number: Page number to retrieve (1-indexed).
        num_records: Number of records per page.

    Returns:
        List of HealthWeight models for the requested page.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_weight from the database
    stmt = (
        select(health_weight_models.HealthWeight)
        .where(health_weight_models.HealthWeight.user_id == user_id)
        .order_by(desc(health_weight_models.HealthWeight.date))
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    return db.execute(stmt).scalars().all()


@core_decorators.handle_db_errors
def get_health_weight_by_date(
    user_id: int, date: str, db: Session
) -> health_weight_models.HealthWeight | None:
    """
    Retrieve health weight record for a user on a specific date.

    Args:
        user_id: User ID.
        date: Date string for the weight record.
        db: Database session.

    Returns:
        HealthWeight model if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the health_weight from the database
    stmt = select(health_weight_models.HealthWeight).where(
        health_weight_models.HealthWeight.date == func.date(date),
        health_weight_models.HealthWeight.user_id == user_id,
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def create_health_weight(
    user_id: int, health_weight: health_weight_schema.HealthWeightCreate, db: Session
) -> health_weight_models.HealthWeight:
    """
    Create a new health weight entry for a user.

    This function creates a new health weight record in the database. If the date is not provided,
    it defaults to the current date. If BMI is not provided, it is automatically calculated
    using the user's height and the provided weight.

    Args:
        user_id (int): The ID of the user for whom the health weight entry is being created.
        health_weight (health_weight_schema.HealthWeightCreate): The health weight data to be created,
            containing fields such as weight, date, and optionally BMI.
        db (Session): The database session used for database operations.

    Returns:
        health_weight_models.HealthWeightCreate: The created health weight model instance.

    Raises:
        HTTPException:
            - 409 Conflict: If a duplicate entry exists for the same date.
            - 500 Internal Server Error: If any other unexpected error occurs during creation.

    Note:
        - The function automatically sets the date to current timestamp if not provided.
        - BMI is calculated automatically if not provided in the input.
        - The database transaction is rolled back in case of any errors.
    """
    try:
        # Check if bmi is None
        if health_weight.bmi is None:
            health_weight = cast(
                health_weight_schema.HealthWeightCreate,
                health_weight_utils.calculate_bmi(health_weight, user_id, db),
            )

        # Create a new health_weight
        db_health_weight = health_weight_models.HealthWeight(
            **health_weight.model_dump(exclude_none=False),
            user_id=user_id,
        )

        # Add the health_weight to the database
        db.add(db_health_weight)
        db.commit()
        db.refresh(db_health_weight)

        # Return the health_weight
        return db_health_weight
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate entry error. Check if there is already a entry created for {health_weight.date}",
        ) from integrity_error


@core_decorators.handle_db_errors
def edit_health_weight(
    user_id: int,
    health_weight: health_weight_schema.HealthWeightUpdate,
    db: Session,
) -> health_weight_models.HealthWeight:
    """
    Edit an existing health weight record for a user.

    Args:
        user_id: User ID who owns the health weight record.
        health_weight: Health weight data to update.
        db: Database session.

    Returns:
        Updated health weight object.

    Raises:
        HTTPException: If record not found or database error.
    """
    # Ensure the health_weight belongs to the user
    if health_weight.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit health weight for another user.",
        )

    # Get the health_weight from the database
    db_health_weight = get_health_weight_by_id_and_user_id(
        health_weight.id, user_id, db
    )

    if db_health_weight is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health weight not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if bmi is None
    if health_weight.bmi is None and health_weight.weight is not None:
        health_weight = cast(
            health_weight_schema.HealthWeightUpdate,
            health_weight_utils.calculate_bmi(health_weight, user_id, db),
        )

    # Dictionary of fields to update if they are not None
    health_weight_data = health_weight.model_dump(exclude_unset=True)
    # Iterate over the fields and update dynamically
    for key, value in health_weight_data.items():
        setattr(db_health_weight, key, value)

    # Commit the transaction and refresh
    db.commit()
    db.refresh(db_health_weight)

    return db_health_weight


@core_decorators.handle_db_errors
def delete_health_weight(user_id: int, health_weight_id: int, db: Session) -> None:
    """
    Delete a health weight record for a user.

    Args:
        user_id: User ID who owns the health weight record.
        health_weight_id: Health weight record ID to delete.
        db: Database session.

    Returns:
        None

    Raises:
        HTTPException: If record not found or database error.
    """
    # Get and delete the health_weight
    db_health_weight = get_health_weight_by_id_and_user_id(
        health_weight_id, user_id, db
    )

    # Check if the health_weight was found
    if db_health_weight is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Health weight with id {health_weight_id} "
                f"for user {user_id} not found"
            ),
        )

    # Delete the record
    db.delete(db_health_weight)
    db.commit()
