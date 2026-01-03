from fastapi import HTTPException, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import health.health_steps.schema as health_steps_schema
import health.health_steps.models as health_steps_models

import core.logger as core_logger


def get_health_steps_number(user_id: int, db: Session) -> int:
    """
    Retrieves the total count of health steps records for a specific user.

    Args:
        user_id (int): The unique identifier of the user whose health steps count is to be retrieved.
        db (Session): The database session object used to query the database.

    Returns:
        int: The total number of health steps records associated with the specified user.

    Raises:
        HTTPException: If a database error or any other exception occurs during the query execution,
                       an HTTPException with status code 500 (Internal Server Error) is raised.
    """
    try:
        # Get the number of health_steps from the database
        return (
            db.query(health_steps_models.HealthSteps)
            .filter(health_steps_models.HealthSteps.user_id == user_id)
            .count()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_steps_number: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_health_steps_by_user_id(
    user_id: int, db: Session
) -> list[health_steps_models.HealthSteps]:
    """
    Retrieve all health steps records for a specific user from the database.

    This function queries the database to fetch all health steps entries associated
    with the given user ID, ordered by date in descending order (most recent first).

    Args:
        user_id (int): The unique identifier of the user whose health steps records
                       are to be retrieved.
        db (Session): The SQLAlchemy database session used to execute the query.

    Returns:
        list[HealthSteps]: A list of HealthSteps model instances representing all
                           health steps records for the specified user, ordered by
                           date in descending order.

    Raises:
        HTTPException: A 500 Internal Server Error exception is raised if any
                       database or unexpected error occurs during the query execution.
                       The original exception is logged before being re-raised.
    """
    try:
        # Get the health_steps from the database
        return (
            db.query(health_steps_models.HealthSteps)
            .filter(health_steps_models.HealthSteps.user_id == user_id)
            .order_by(desc(health_steps_models.HealthSteps.date))
            .all()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_health_steps_by_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_steps_with_pagination(
    user_id: int, db: Session, page_number: int = 1, num_records: int = 5
) -> list[health_steps_models.HealthSteps]:
    """
    Retrieve paginated health steps records for a specific user.

    This function queries the database to fetch health steps records for a given user,
    with support for pagination. Results are ordered by date in descending order.

    Args:
        user_id (int): The ID of the user whose health steps records are to be retrieved.
        db (Session): The database session object used for querying.
        page_number (int, optional): The page number to retrieve. Defaults to 1.
        num_records (int, optional): The number of records per page. Defaults to 5.

    Returns:
        list[health_steps_models.HealthSteps]: A list of HealthSteps model instances
            representing the user's health steps records for the specified page.

    Raises:
        HTTPException: A 500 Internal Server Error exception is raised if any
            database operation fails or an unexpected error occurs during execution.
    """
    try:
        # Get the health_steps from the database
        return (
            db.query(health_steps_models.HealthSteps)
            .filter(health_steps_models.HealthSteps.user_id == user_id)
            .order_by(desc(health_steps_models.HealthSteps.date))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_steps_with_pagination: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_steps_by_date(
    user_id: int, date: str, db: Session
) -> health_steps_models.HealthSteps | None:
    """
    Retrieve health steps data for a specific user and date.

    This function queries the database to find health steps records matching
    the specified user ID and date.

    Args:
        user_id (int): The unique identifier of the user.
        date (str): The date for which to retrieve health steps data (format: YYYY-MM-DD).
        db (Session): The database session object for executing queries.

    Returns:
        health_steps_models.HealthSteps | None: The health steps record if found,
            otherwise None.

    Raises:
        HTTPException: A 500 Internal Server Error if an exception occurs during
            the database query operation.
    """
    try:
        # Get the health_steps from the database
        return (
            db.query(health_steps_models.HealthSteps)
            .filter(
                health_steps_models.HealthSteps.date == func.date(date),
                health_steps_models.HealthSteps.user_id == user_id,
            )
            .first()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_steps_by_date: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_health_steps(
    user_id: int, health_steps: health_steps_schema.HealthSteps, db: Session
) -> health_steps_schema.HealthSteps:
    """
    Create a new health steps record for a user.

    This function creates a new health steps entry in the database for the specified user.
    If no date is provided, it defaults to the current date/time.

    Args:
        user_id (int): The ID of the user for whom the health steps record is being created.
        health_steps (health_steps_schema.HealthSteps): The health steps data to be created.
            The 'id' and 'user_id' fields are excluded from the input as they are set internally.
        db (Session): The database session for executing the database operations.

    Returns:
        health_steps_schema.HealthSteps: The created health steps record with the assigned ID.

    Raises:
        HTTPException:
            - 409 Conflict: If a health steps entry already exists for the given date.
            - 500 Internal Server Error: If any other unexpected error occurs during creation.
    """
    try:
        # Check if date is None
        if health_steps.date is None:
            # Set the date to the current date
            health_steps.date = func.now()

        # Create a new health_steps
        db_health_steps = health_steps_models.HealthSteps(
            **health_steps.model_dump(exclude={"id", "user_id"}, exclude_none=False),
            user_id=user_id,
        )

        # Add the health_steps to the database
        db.add(db_health_steps)
        db.commit()
        db.refresh(db_health_steps)

        # Set the id of the health_steps
        health_steps.id = db_health_steps.id

        # Return the health_steps
        return health_steps
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate entry error. Check if there is already a entry created for {health_steps.date}",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_health_steps: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_health_steps(
    user_id, health_steps: health_steps_schema.HealthSteps, db: Session
) -> health_steps_schema.HealthSteps:
    """
    Edit health steps record for a specific user.

    This function updates an existing health steps record in the database for a given user.
    It performs validation to ensure the record exists and belongs to the specified user
    before applying updates.

    Args:
        user_id: The ID of the user who owns the health steps record.
        health_steps (health_steps_schema.HealthSteps): The health steps object containing
            the ID of the record to update and the fields to be modified.
        db (Session): The database session used for querying and committing changes.

    Returns:
        health_steps_schema.HealthSteps: The updated health steps object.

    Raises:
        HTTPException:
            - 404 NOT_FOUND: If the health steps record is not found or doesn't belong
              to the specified user.
            - 500 INTERNAL_SERVER_ERROR: If an unexpected error occurs during the update
              process.
    """
    try:
        # Get the health_steps from the database
        db_health_steps = (
            db.query(health_steps_models.HealthSteps)
            .filter(
                health_steps_models.HealthSteps.id == health_steps.id,
                health_steps_models.HealthSteps.user_id == user_id,
            )
            .first()
        )

        if db_health_steps is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Health steps not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Dictionary of the fields to update if they are not None
        health_steps_data = health_steps.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_health_steps dynamically
        for key, value in health_steps_data.items():
            setattr(db_health_steps, key, value)

        # Commit the transaction
        db.commit()

        return health_steps
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in edit_health_steps: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_health_steps(user_id: int, health_steps_id: int, db: Session) -> None:
    """
    Delete a health steps record for a specific user.

    This function deletes a health steps entry from the database based on the provided
    health_steps_id and user_id. It ensures that the record belongs to the specified user
    before deletion.

    Args:
        user_id (int): The ID of the user who owns the health steps record.
        health_steps_id (int): The ID of the health steps record to delete.
        db (Session): The database session object for executing queries.

    Returns:
        None

    Raises:
        HTTPException:
            - 404 NOT FOUND if the health steps record with the given ID
              for the specified user is not found.
            - 500 INTERNAL SERVER ERROR if any other exception occurs during
              the deletion process.
    """
    try:
        # Delete the health_steps
        num_deleted = (
            db.query(health_steps_models.HealthSteps)
            .filter(
                health_steps_models.HealthSteps.id == health_steps_id,
                health_steps_models.HealthSteps.user_id == user_id,
            )
            .delete()
        )

        # Check if the health_steps was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Health steps with id {health_steps_id} for user {user_id} not found",
            )

        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in delete_health_steps: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
