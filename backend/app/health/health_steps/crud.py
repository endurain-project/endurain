from fastapi import HTTPException, status
from sqlalchemy import func, desc, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import health.health_steps.schema as health_steps_schema
import health.health_steps.models as health_steps_models

import core.logger as core_logger


def get_health_steps_number(user_id: int, db: Session) -> int:
    """
    Retrieve total count of health steps records for a user.

    Args:
        user_id: User ID to count records for.
        db: Database session.

    Returns:
        Total number of health steps records.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the number of health_steps from the database
        stmt = (
            select(func.count())
            .select_from(health_steps_models.HealthSteps)
            .where(health_steps_models.HealthSteps.user_id == user_id)
        )
        result = db.execute(stmt).scalar()
        return result if result is not None else 0
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_steps_number: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_all_health_steps_by_user_id(
    user_id: int, db: Session
) -> list[health_steps_models.HealthSteps]:
    """
    Retrieve all health steps records for a user.

    Args:
        user_id: User ID to fetch records for.
        db: Database session.

    Returns:
        List of HealthSteps models ordered by date descending.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the health_steps from the database
        stmt = (
            select(health_steps_models.HealthSteps)
            .where(health_steps_models.HealthSteps.user_id == user_id)
            .order_by(desc(health_steps_models.HealthSteps.date))
        )
        return db.execute(stmt).scalars().all()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_all_health_steps_by_user_id: " f"{db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_health_steps_by_id_and_user_id(
    health_steps_id: int, user_id: int, db: Session
) -> health_steps_models.HealthSteps | None:
    """
    Retrieve health steps records by ID and user ID.
    Args:
        health_steps_id: Health steps record ID to fetch.
        user_id: User ID to fetch records for.
        db: Database session.

    Returns:
        HealthSteps model if found, None otherwise.
    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the health_steps from the database
        stmt = select(health_steps_models.HealthSteps).where(
            health_steps_models.HealthSteps.id == health_steps_id,
            health_steps_models.HealthSteps.user_id == user_id,
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_steps_by_id_and_user_id: " f"{db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_health_steps_with_pagination(
    user_id: int,
    db: Session,
    page_number: int = 1,
    num_records: int = 5,
) -> list[health_steps_models.HealthSteps]:
    """
    Retrieve paginated health steps records for a user.

    Args:
        user_id: User ID to fetch records for.
        db: Database session.
        page_number: Page number to retrieve (1-indexed).
        num_records: Number of records per page.

    Returns:
        List of HealthSteps models for the requested page.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the health_steps from the database
        stmt = (
            select(health_steps_models.HealthSteps)
            .where(health_steps_models.HealthSteps.user_id == user_id)
            .order_by(desc(health_steps_models.HealthSteps.date))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
        )
        return db.execute(stmt).scalars().all()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_steps_with_pagination: " f"{db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_health_steps_by_date(
    user_id: int, date: str, db: Session
) -> health_steps_models.HealthSteps | None:
    """
    Retrieve health steps record for a user on a specific date.

    Args:
        user_id: User ID.
        date: Date string for the steps record.
        db: Database session.

    Returns:
        HealthSteps model if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the health_steps from the database
        stmt = select(health_steps_models.HealthSteps).where(
            health_steps_models.HealthSteps.date == func.date(date),
            health_steps_models.HealthSteps.user_id == user_id,
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_steps_by_date: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def create_health_steps(
    user_id: int,
    health_steps: health_steps_schema.HealthStepsCreate,
    db: Session,
) -> health_steps_models.HealthSteps:
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
        return db_health_steps
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Duplicate entry error. Check if there is already "
                f"a entry created for {health_steps.date}"
            ),
        ) from integrity_error
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in create_health_steps: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def edit_health_steps(
    user_id: int,
    health_steps: health_steps_schema.HealthStepsUpdate,
    db: Session,
) -> health_steps_models.HealthSteps:
    """
    Edit health steps record for a user.

    Args:
        user_id: User ID who owns the record.
        health_steps: Health steps data to update.
        db: Database session.

    Returns:
        Updated HealthSteps model.

    Raises:
        HTTPException: 403 if trying to edit other user record, 404 if not
            found, 500 if database error.
    """
    try:
        # Ensure the health_steps belongs to the user
        if health_steps.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot edit health steps for another user.",
            )

        # Get the health_steps from the database
        db_health_steps = get_health_steps_by_id_and_user_id(
            health_steps.id, user_id, db
        )

        if db_health_steps is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Health steps not found",
            ) from None

        # Dictionary of the fields to update if they are not None
        health_steps_data = health_steps.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_health_steps dynamically
        for key, value in health_steps_data.items():
            setattr(db_health_steps, key, value)

        # Commit the transaction
        db.commit()
        # Refresh the object to ensure it reflects database state
        db.refresh(db_health_steps)

        return db_health_steps
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in edit_health_steps: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


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
    try:
        # Get the record first to ensure it exists
        db_health_steps = get_health_steps_by_id_and_user_id(
            health_steps_id, user_id, db
        )

        # Check if the health_steps was found
        if db_health_steps is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Health steps not found",
            ) from None

        # Delete the health_steps
        db.delete(db_health_steps)
        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in delete_health_steps: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err
