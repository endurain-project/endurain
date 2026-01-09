from fastapi import HTTPException, status
from sqlalchemy import func, desc, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import health.health_sleep.schema as health_sleep_schema
import health.health_sleep.models as health_sleep_models

import core.logger as core_logger


def get_health_sleep_number(user_id: int, db: Session) -> int:
    """
    Retrieve total count of health sleep records for a user.

    Args:
        user_id: User ID to count records for.
        db: Database session.

    Returns:
        Total number of health sleep records.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the number of health_sleep from the database
        stmt = (
            select(func.count())
            .select_from(health_sleep_models.HealthSleep)
            .where(health_sleep_models.HealthSleep.user_id == user_id)
        )
        result = db.execute(stmt).scalar()
        return result if result is not None else 0
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_sleep_number: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_all_health_sleep_by_user_id(
    user_id: int, db: Session
) -> list[health_sleep_models.HealthSleep]:
    """
    Retrieve all sleep health records for a user.

    Args:
        user_id: User ID to fetch records for.
        db: Database session.

    Returns:
        List of HealthSleep models ordered by date descending.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the health_sleep from the database
        stmt = (
            select(health_sleep_models.HealthSleep)
            .where(health_sleep_models.HealthSleep.user_id == user_id)
            .order_by(desc(health_sleep_models.HealthSleep.date))
        )
        return db.execute(stmt).scalars().all()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_all_health_sleep_by_user_id: " f"{db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_health_sleep_by_id_and_user_id(
    health_sleep_id: int, user_id: int, db: Session
) -> health_sleep_models.HealthSleep | None:
    """
    Retrieve health sleep records by ID and user ID.

    Args:
        health_sleep_id: Health sleep record ID to fetch.
        user_id: User ID to fetch records for.
        db: Database session.

    Returns:
        HealthSleep model if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the health_sleep from the database
        stmt = select(health_sleep_models.HealthSleep).where(
            health_sleep_models.HealthSleep.id == health_sleep_id,
            health_sleep_models.HealthSleep.user_id == user_id,
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_sleep_by_id_and_user_id: " f"{db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_health_sleep_with_pagination(
    user_id: int,
    db: Session,
    page_number: int = 1,
    num_records: int = 5,
) -> list[health_sleep_models.HealthSleep]:
    """
    Retrieve paginated health sleep records for a user.

    Args:
        user_id: User ID to fetch records for.
        db: Database session.
        page_number: Page number to retrieve (1-indexed).
        num_records: Number of records per page.

    Returns:
        List of HealthSleep models for the requested page.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the health_sleep from the database
        stmt = (
            select(health_sleep_models.HealthSleep)
            .where(health_sleep_models.HealthSleep.user_id == user_id)
            .order_by(desc(health_sleep_models.HealthSleep.date))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
        )
        return db.execute(stmt).scalars().all()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_sleep_with_pagination: " f"{db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_health_sleep_by_date(
    user_id: int, date: str, db: Session
) -> health_sleep_models.HealthSleep | None:
    """
    Retrieve health sleep record for a user on a specific date.

    Args:
        user_id: User ID.
        date: Date string for the sleep record.
        db: Database session.

    Returns:
        HealthSleep model if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the health_sleep from the database
        stmt = select(health_sleep_models.HealthSleep).where(
            health_sleep_models.HealthSleep.date == func.date(date),
            health_sleep_models.HealthSleep.user_id == user_id,
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_sleep_by_date: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def create_health_sleep(
    user_id: int,
    health_sleep: health_sleep_schema.HealthSleepCreate,
    db: Session,
) -> health_sleep_models.HealthSleep:
    """
    Create a new health sleep record for a user.

    Args:
        user_id: User ID for the sleep record.
        health_sleep: Health sleep data to create.
        db: Database session.

    Returns:
        Created health sleep record with assigned ID.

    Raises:
        HTTPException: 409 if duplicate entry, 500 if database
            error.
    """
    try:
        # Create a new health_sleep
        db_health_sleep = health_sleep_models.HealthSleep(
            **health_sleep.model_dump(
                exclude_none=False,
            ),
            user_id=user_id,
        )

        # Add the health_sleep to the database
        db.add(db_health_sleep)
        db.commit()
        db.refresh(db_health_sleep)

        # Return the created health_sleep model
        return db_health_sleep
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Duplicate entry error. Check if there is "
                f"already an entry created for {health_sleep.date}"
            ),
        ) from integrity_error
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in create_health_sleep: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def edit_health_sleep(
    user_id: int,
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    db: Session,
) -> health_sleep_models.HealthSleep:
    """
    Edit an existing health sleep record for a user.

    Args:
        user_id: User ID whose sleep record is being edited.
        health_sleep: Updated health sleep data.
        db: Database session.

    Returns:
        Updated HealthSleep model.

    Raises:
        HTTPException: 403 if trying to edit other user record, 404 if not
            found, 500 if database error.
    """
    try:
        # Ensure the health_sleep belongs to the user
        if health_sleep.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot edit health sleep for another user.",
            )

        # Get the health_sleep from the database
        db_health_sleep = get_health_sleep_by_id_and_user_id(
            health_sleep.id, user_id, db
        )

        if db_health_sleep is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Health sleep not found",
            )

        # Dictionary of the fields to update if they are not None
        health_sleep_data = health_sleep.model_dump(exclude_unset=True, mode="json")
        # Iterate over fields and update dynamically
        for key, value in health_sleep_data.items():
            setattr(db_health_sleep, key, value)

        # Commit the transaction
        db.commit()
        db.refresh(db_health_sleep)

        return db_health_sleep
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in edit_health_sleep: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def delete_health_sleep(user_id: int, health_sleep_id: int, db: Session) -> None:
    """
    Delete a health sleep record for a specific user.

    Args:
        user_id: User ID who owns the sleep record.
        health_sleep_id: Sleep record ID to delete.
        db: Database session.

    Returns:
        None

    Raises:
        HTTPException: 404 if not found, 500 if database error.
    """
    try:
        # Get the record to delete
        db_health_sleep = get_health_sleep_by_id_and_user_id(
            health_sleep_id, user_id, db
        )

        # Check if the health_sleep was found
        if db_health_sleep is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Health sleep with id {health_sleep_id} "
                    f"for user {user_id} not found"
                ),
            )

        # Delete the record
        db.delete(db_health_sleep)
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in delete_health_sleep: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err
