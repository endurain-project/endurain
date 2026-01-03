from fastapi import HTTPException, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import health.health_weight.schema as health_weight_schema
import health.health_weight.models as health_weight_models
import health.health_weight.utils as health_weight_utils

import core.logger as core_logger


def get_all_health_weight(
    db: Session,
) -> list[health_weight_models.HealthWeight]:
    """
    Retrieve all health weight records from the database.

    Queries the database for all health weight entries and returns them ordered
    by date in descending order (most recent first).

    Args:
        db (Session): SQLAlchemy database session for executing queries.

    Returns:
        list[HealthWeight]: A list of all HealthWeight model instances ordered
            by date (descending).

    Raises:
        HTTPException: A 500 Internal Server Error if the database query fails
            or any other exception occurs during execution.
    """
    try:
        # Get the health_weight from the database and return it
        return (
            db.query(health_weight_models.HealthWeight)
            .order_by(desc(health_weight_models.HealthWeight.date))
            .all()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_health_weight: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_weight_number(user_id: int, db: Session) -> int:
    """
    Retrieves the total count of health weight records for a specific user.

    Args:
        user_id (int): The unique identifier of the user whose health weight records are to be counted.
        db (Session): The database session object used to execute the query.

    Returns:
        int: The total number of health weight records associated with the specified user.

    Raises:
        HTTPException: A 500 Internal Server Error is raised if any exception occurs during
                       the database query operation. The original exception is logged before
                       raising the HTTPException.
    """
    try:
        # Get the number of health_weight from the database
        return (
            db.query(health_weight_models.HealthWeight)
            .filter(health_weight_models.HealthWeight.user_id == user_id)
            .count()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_weight_number: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_health_weight_by_user_id(
    user_id: int, db: Session
) -> list[health_weight_models.HealthWeight]:
    """
    Retrieve all health weight records for a specific user.

    This function queries the database to fetch all health weight entries associated
    with a given user ID, ordered by date in descending order (most recent first).

    Args:
        user_id (int): The unique identifier of the user whose health weight records
            are to be retrieved.
        db (Session): SQLAlchemy database session object for executing queries.

    Returns:
        list: A list of HealthWeight model instances containing all weight records
            for the specified user, ordered by date (newest to oldest).

    Raises:
        HTTPException: Returns a 500 Internal Server Error if any database operation
            or unexpected error occurs during the query execution.
    """
    try:
        # Get the health_weight from the database
        return (
            db.query(health_weight_models.HealthWeight)
            .filter(health_weight_models.HealthWeight.user_id == user_id)
            .order_by(desc(health_weight_models.HealthWeight.date))
            .all()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_health_weight_by_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_weight_with_pagination(
    user_id: int, db: Session, page_number: int = 1, num_records: int = 5
) -> list[health_weight_models.HealthWeight]:
    """
    Retrieve paginated health weight records for a specific user.

    This function queries the database to fetch health weight records for a given user
    with pagination support. Results are ordered by date in descending order (most recent first).

    Args:
        user_id (int): The unique identifier of the user whose health weight records to retrieve.
        db (Session): The SQLAlchemy database session used for querying.
        page_number (int, optional): The page number to retrieve. Defaults to 1.
        num_records (int, optional): The number of records per page. Defaults to 5.

    Returns:
        list[health_weight_models.HealthWeight]: A list of HealthWeight model instances
            for the specified page, ordered by date in descending order.

    Raises:
        HTTPException: Raises a 500 Internal Server Error if any exception occurs during
            the database query operation.
    """
    try:
        # Get the health_weight from the database with pagination and return it
        return (
            db.query(health_weight_models.HealthWeight)
            .filter(health_weight_models.HealthWeight.user_id == user_id)
            .order_by(desc(health_weight_models.HealthWeight.date))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_weight_with_pagination: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_weight_by_date(
    user_id: int, date: str, db: Session
) -> health_weight_models.HealthWeight | None:
    """
    Retrieve a health weight record for a specific user and date.

    This function queries the database to find a health weight entry matching
    the provided user ID and date.

    Args:
        user_id (int): The unique identifier of the user.
        date (str): The date string for which to retrieve the health weight record.
        db (Session): The database session object for executing queries.

    Returns:
        HealthWeight | None: The health weight record if found, None otherwise.

    Raises:
        HTTPException: A 500 Internal Server Error if the database query fails
                       or any other exception occurs during execution.
    """
    try:
        # Get the health_weight from the database and return it
        return (
            db.query(health_weight_models.HealthWeight)
            .filter(
                health_weight_models.HealthWeight.date == func.date(date),
                health_weight_models.HealthWeight.user_id == user_id,
            )
            .first()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_weight_by_date: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_health_weight(
    user_id: int, health_weight: health_weight_schema.HealthWeight, db: Session
) -> health_weight_schema.HealthWeight:
    """
    Create a new health weight entry for a user.

    This function creates a new health weight record in the database. If the date is not provided,
    it defaults to the current date. If BMI is not provided, it is automatically calculated
    using the user's height and the provided weight.

    Args:
        user_id (int): The ID of the user for whom the health weight entry is being created.
        health_weight (health_weight_schema.HealthWeight): The health weight data to be created,
            containing fields such as weight, date, and optionally BMI.
        db (Session): The database session used for database operations.

    Returns:
        health_weight_schema.HealthWeight: The created health weight entry with its assigned ID.

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
        # Check if date is None
        if health_weight.date is None:
            # Set the date to the current date
            health_weight.date = func.now()

        # Check if bmi is None
        if health_weight.bmi is None:
            health_weight = health_weight_utils.calculate_bmi(
                health_weight, user_id, db
            )

        # Create a new health_weight
        db_health_weight = health_weight_models.HealthWeight(
            **health_weight.model_dump(exclude={"id", "user_id"}, exclude_none=False),
            user_id=user_id,
        )

        # Add the health_weight to the database
        db.add(db_health_weight)
        db.commit()
        db.refresh(db_health_weight)

        # Set the id of the health_weight
        health_weight.id = db_health_weight.id

        # Return the health_weight
        return health_weight
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate entry error. Check if there is already a entry created for {health_weight.date}",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_health_weight: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_health_weight(
    user_id, health_weight: health_weight_schema.HealthWeight, db: Session
) -> health_weight_schema.HealthWeight:
    """
    Edit an existing health weight record for a user.

    This function updates a health weight entry in the database for a specific user.
    It automatically calculates BMI if weight is provided but BMI is not. The function
    only updates fields that are explicitly set in the input schema.

    Args:
        user_id: The ID of the user who owns the health weight record.
        health_weight (health_weight_schema.HealthWeight): The health weight data to update,
            containing the record ID and fields to be modified.
        db (Session): The database session for executing queries.

    Returns:
        health_weight_schema.HealthWeight: The updated health weight object with all current values.

    Raises:
        HTTPException:
            - 404 NOT_FOUND if the health weight record doesn't exist or doesn't belong to the user.
            - 500 INTERNAL_SERVER_ERROR if a database error or unexpected exception occurs.

    Note:
        - Only fields present in the input schema (exclude_unset=True) will be updated.
        - If BMI is None but weight is provided, BMI will be automatically calculated.
        - The database transaction is automatically rolled back on error.
    """
    try:
        # Get the health_weight from the database
        db_health_weight = (
            db.query(health_weight_models.HealthWeight)
            .filter(
                health_weight_models.HealthWeight.id == health_weight.id,
                health_weight_models.HealthWeight.user_id == user_id,
            )
            .first()
        )

        if db_health_weight is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Health weight not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if bmi is None
        if health_weight.bmi is None and health_weight.weight is not None:
            health_weight = health_weight_utils.calculate_bmi(
                health_weight, user_id, db
            )

        # Dictionary of the fields to update if they are not None
        health_weight_data = health_weight.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_health_weight dynamically
        for key, value in health_weight_data.items():
            setattr(db_health_weight, key, value)

        # Commit the transaction
        db.commit()

        return health_weight
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in edit_health_weight: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_health_weight(user_id: int, health_weight_id: int, db: Session) -> None:
    """
    Delete a health weight record for a specific user.

    This function deletes a health weight entry from the database identified by
    the health_weight_id and user_id. If the record is not found, it raises a
    404 HTTPException. Any database errors will trigger a rollback and raise a
    500 HTTPException.

    Args:
        user_id (int): The ID of the user who owns the health weight record.
        health_weight_id (int): The ID of the health weight record to delete.
        db (Session): The database session object used for querying and committing.

    Returns:
        None

    Raises:
        HTTPException:
            - 404 NOT_FOUND if the health weight record with the specified ID
              for the given user is not found.
            - 500 INTERNAL_SERVER_ERROR if a database error occurs during deletion.
    """
    try:
        # Delete the health_weight
        num_deleted = (
            db.query(health_weight_models.HealthWeight)
            .filter(
                health_weight_models.HealthWeight.id == health_weight_id,
                health_weight_models.HealthWeight.user_id == user_id,
            )
            .delete()
        )

        # Check if the health_weight was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Health weight with id {health_weight_id} for user {user_id} not found",
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
            f"Error in delete_health_weight: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
