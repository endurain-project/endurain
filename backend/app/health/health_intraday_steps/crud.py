import os
from datetime import datetime, time as datetime_time, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, desc, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import health.health_intraday_steps.schema as health_intraday_steps_schema
import health.health_intraday_steps.models as health_intraday_steps_models

import core.logger as core_logger

from zoneinfo import ZoneInfo


def get_health_intraday_steps_number(user_id: int, db: Session) -> int:
    """
    Retrieve total count of health intraday steps records for a user.

    Args:
        user_id: User ID to count records for.
        db: Database session.

    Returns:
        Total number of health intraday steps records.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the number of health_intraday_steps from the database
        stmt = (
            select(func.count())
            .select_from(health_intraday_steps_models.HealthIntradaySteps)
            .where(health_intraday_steps_models.HealthIntradaySteps.user_id == user_id)
        )
        result = db.execute(stmt).scalar()
        return result if result is not None else 0
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_intraday_steps_number: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err
    

def get_health_intraday_steps_number_by_date(
        user_id: int, 
        date: str, 
        db: Session
) -> list[health_intraday_steps_models.HealthIntradaySteps]:
    """
    Retrieve total count of health intraday steps records for a user and given date.

    Args:
        user_id: User ID to count records for.
        date: Date string for the step count.
        db: Database session.

    Returns:
        Step records.

    Raises:
        HTTPException: If database error occurs.
    """
    tz =  ZoneInfo(os.environ.get("TZ", "UTC"))
    date_dt = datetime.strptime(date, "%Y-%m-%d").date()

    local_start = datetime.combine(date_dt, datetime_time.min, tzinfo=tz)
    local_end = datetime.combine(date_dt + timedelta(days=1), datetime_time.min, tzinfo=tz)

    utc_start = local_start.astimezone(ZoneInfo("UTC"))
    utc_end = local_end.astimezone(ZoneInfo("UTC"))

    return get_health_intraday_steps_by_timerange(user_id, utc_start, utc_end, db)


def get_all_health_intraday_steps_by_user_id(
    user_id: int, db: Session
) -> list[health_intraday_steps_models.HealthIntradaySteps]:
    """
    Retrieve all health intraday steps records for a user.

    Args:
        user_id: User ID to fetch records for.
        db: Database session.

    Returns:
        List of HealthIntradaySteps models ordered by date descending.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the health_intraday_steps from the database
        stmt = (
            select(health_intraday_steps_models.HealthIntradaySteps)
            .where(health_intraday_steps_models.HealthIntradaySteps.user_id == user_id)
            .order_by(desc(health_intraday_steps_models.HealthIntradaySteps.timestamp))
        )
        return db.execute(stmt).scalars().all()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_all_health_intraday_steps_by_user_id: " f"{db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_health_intraday_steps_by_id_and_user_id(
    health_intraday_steps_id: int, user_id: int, db: Session
) -> health_intraday_steps_models.HealthIntradaySteps | None:
    """
    Retrieve health intraday steps record by ID and user ID.
    Args:
        health_intraday_steps_id: Health intraday steps record ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        HealthIntradaySteps model if found, None otherwise.
    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the health_intraday_steps from the database
        stmt = select(health_intraday_steps_models.HealthIntradaySteps).where(
            health_intraday_steps_models.HealthIntradaySteps.id == health_intraday_steps_id,
            health_intraday_steps_models.HealthIntradaySteps.user_id == user_id,
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_intraday_steps_by_id_and_user_id: " f"{db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_health_intraday_steps_with_pagination(
    user_id: int,
    db: Session,
    page_number: int = 1,
    num_records: int = 5,
) -> list[health_intraday_steps_models.HealthIntradaySteps]:
    """
    Retrieve paginated health intraday steps records for a user.

    Args:
        user_id: User ID to fetch records for.
        db: Database session.
        page_number: Page number to retrieve (1-indexed).
        num_records: Number of records per page.

    Returns:
        List of HealthIntradaySteps models for the requested page.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the health_intraday_steps from the database
        stmt = (
            select(health_intraday_steps_models.HealthIntradaySteps)
            .where(health_intraday_steps_models.HealthIntradaySteps.user_id == user_id)
            .order_by(desc(health_intraday_steps_models.HealthIntradaySteps.timestamp))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
        )
        return db.execute(stmt).scalars().all()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_health_intraday_steps_with_pagination: " f"{db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_health_intraday_steps_by_timerange(
    user_id: int,
    start_time: datetime,
    end_time: datetime,
    db: Session,
) -> list[health_intraday_steps_models.HealthIntradaySteps]:
    """
    Retrieve health intraday steps records for a user within a time range.

    Args:
        user_id: User ID.
        start_time: Start datetime (inclusive).
        end_time: End datetime (exclusive).
        db: Database session.

    Returns:
        List of HealthIntradaySteps models.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        stmt = (
            select(health_intraday_steps_models.HealthIntradaySteps)
            .where(
                health_intraday_steps_models.HealthIntradaySteps.user_id == user_id,
                health_intraday_steps_models.HealthIntradaySteps.timestamp >= start_time,
                health_intraday_steps_models.HealthIntradaySteps.timestamp < end_time,
            )
            .order_by(health_intraday_steps_models.HealthIntradaySteps.timestamp)
        )

        return db.execute(stmt).scalars().all()

    except SQLAlchemyError as db_err:
        core_logger.print_to_log(
            f"Database error in get_health_intraday_steps_by_timerange: {db_err}",
            "error",
            exc=db_err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def create_health_intraday_steps(
    user_id: int,
    health_intraday_steps: list[health_intraday_steps_schema.HealthIntradayStepsCreate],
    db: Session,
) -> list[health_intraday_steps_models.HealthIntradaySteps]:
    """
    Create multiple health intraday step records for a user.

    Args:
        user_id: User ID for the record owner.
        health_intraday_steps: Health intraday steps data to create.
        db: Database session.

    Returns:
        Created health intraday step records.

    Raises:
        HTTPException: If duplicate entry or database error.
    """
    created = []
    try:
        for step in health_intraday_steps:
            # Create a new health_intraday_steps
            db_health_intraday_steps = health_intraday_steps_models.HealthIntradaySteps(
                **step.model_dump(exclude_none=False),
                user_id=user_id,
            )

            # Add the health_intraday_steps to the database
            db.add(db_health_intraday_steps)
            db.commit()
            db.refresh(db_health_intraday_steps)

            # Return the health_intraday_steps
            created.append(db_health_intraday_steps)

        return created
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Duplicate entry error. Check if there is already "
                f"a entry created for {step.timestamp}"
            ),
        ) from integrity_error
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in create_health_intraday_steps: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def edit_health_intraday_steps(
    user_id: int,
    health_intraday_steps: health_intraday_steps_schema.HealthIntradayStepsUpdate,
    db: Session,
) -> health_intraday_steps_models.HealthIntradaySteps:
    """
    Edit health intraday steps record for a user.

    Args:
        user_id: User ID who owns the record.
        health_intraday_steps: Health intraday steps data to update.
        db: Database session.

    Returns:
        Updated HealthIntradaySteps model.

    Raises:
        HTTPException: 403 if trying to edit other user record, 404 if not
            found, 500 if database error.
    """
    try:
        # Ensure the health_intraday_steps belongs to the user
        if health_intraday_steps.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot edit health intraday steps for another user.",
            )

        # Get the health_intraday_steps from the database
        db_health_intraday_steps = get_health_intraday_steps_by_id_and_user_id(
            health_intraday_steps.id, user_id, db
        )

        if db_health_intraday_steps is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Health intraday steps not found",
            ) from None

        # Dictionary of the fields to update if they are not None
        health_intraday_steps_data = health_intraday_steps.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_health_intraday_steps dynamically
        for key, value in health_intraday_steps_data.items():
            setattr(db_health_intraday_steps, key, value)

        # Commit the transaction
        db.commit()
        # Refresh the object to ensure it reflects database state
        db.refresh(db_health_intraday_steps)

        return db_health_intraday_steps
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in edit_health_intraday_steps: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def delete_health_intraday_steps(user_id: int, health_intraday_steps_id: int, db: Session) -> None:
    """
    Delete a health intraday steps record for a user.

    Args:
        user_id: User ID who owns the record.
        health_intraday_steps_id: Health intraday steps record ID to delete.
        db: Database session.

    Returns:
        None

    Raises:
        HTTPException: If record not found or database error.
    """
    try:
        # Get the record first to ensure it exists
        db_health_intraday_steps = get_health_intraday_steps_by_id_and_user_id(
            health_intraday_steps_id, user_id, db
        )

        # Check if the health_intraday_steps was found
        if db_health_intraday_steps is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Health intraday steps not found",
            ) from None

        # Delete the health_intraday_steps
        db.delete(db_health_intraday_steps)
        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in delete_health_intraday_steps: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err
