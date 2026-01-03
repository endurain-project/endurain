from fastapi import HTTPException, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import health.health_sleep.schema as health_sleep_schema
import health.health_sleep.models as health_sleep_models

import core.logger as core_logger


def get_health_sleep_number(user_id: int, db: Session) -> int:
    """
    Retrieve the total count of health sleep records for a specific user.

    This function queries the database to count all health sleep entries
    associated with the given user ID.

    Args:
        user_id (int): The unique identifier of the user whose health sleep
            records are to be counted.
        db (Session): The SQLAlchemy database session used to execute the query.

    Returns:
        int: The total number of health sleep records for the specified user.

    Raises:
        HTTPException: A 500 Internal Server Error exception is raised if any
            error occurs during the database query operation. The original
            exception is logged before raising the HTTPException.
    """
    try:
        # Get the number of health_sleep from the database
        return (
            db.query(health_sleep_models.HealthSleep)
            .filter(health_sleep_models.HealthSleep.user_id == user_id)
            .count()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_sleep_number: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_health_sleep_by_user_id(
    user_id: int, db: Session
) -> list[health_sleep_models.HealthSleep]:
    """
    Retrieve all sleep health records for a specific user from the database.

    This function queries the database for all health sleep entries associated with
    a given user ID, ordered by date in descending order (most recent first).

    Args:
        user_id (int): The unique identifier of the user whose sleep records are to be retrieved.
        db (Session): The SQLAlchemy database session used to execute the query.

    Returns:
        list[HealthSleep]: A list of HealthSleep model instances for the specified user,
                           ordered by date in descending order. Returns an empty list if
                           no records are found.

    Raises:
        HTTPException: A 500 Internal Server Error exception is raised if any database
                       error or unexpected exception occurs during the query execution.
    """
    try:
        # Get the health_sleep from the database
        return (
            db.query(health_sleep_models.HealthSleep)
            .filter(health_sleep_models.HealthSleep.user_id == user_id)
            .order_by(desc(health_sleep_models.HealthSleep.date))
            .all()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_health_sleep_by_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_sleep_with_pagination(
    user_id: int, db: Session, page_number: int = 1, num_records: int = 5
) -> list[health_sleep_models.HealthSleep]:
    """
    Retrieve paginated health sleep records for a specific user.

    This function queries the database to fetch health sleep records for a given user,
    ordered by date in descending order, with pagination support.

    Args:
        user_id (int): The unique identifier of the user whose health sleep records are to be retrieved.
        db (Session): The database session object used to execute the query.
        page_number (int, optional): The page number to retrieve. Defaults to 1.
        num_records (int, optional): The number of records to retrieve per page. Defaults to 5.

    Returns:
        list[HealthSleep]: A list of HealthSleep model instances representing the user's sleep records
                           for the specified page.

    Raises:
        HTTPException: A 500 Internal Server Error is raised if any exception occurs during
                       the database query operation.
    """
    try:
        # Get the health_sleep from the database
        return (
            db.query(health_sleep_models.HealthSleep)
            .filter(health_sleep_models.HealthSleep.user_id == user_id)
            .order_by(desc(health_sleep_models.HealthSleep.date))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_sleep_with_pagination: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_sleep_by_date(
    user_id: int, date: str, db: Session
) -> health_sleep_models.HealthSleep | None:
    """
    Retrieve a health sleep record for a specific user and date.

    Args:
        user_id (int): The unique identifier of the user.
        date (str): The date for which to retrieve the health sleep record.
        db (Session): The database session object.

    Returns:
        health_sleep_models.HealthSleep | None: The health sleep record if found, None otherwise.

    Raises:
        HTTPException: If a database error occurs, raises a 500 Internal Server Error.
    """
    try:
        # Get the health_sleep from the database
        return (
            db.query(health_sleep_models.HealthSleep)
            .filter(
                health_sleep_models.HealthSleep.date == func.date(date),
                health_sleep_models.HealthSleep.user_id == user_id,
            )
            .first()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_sleep_by_date: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_health_sleep(
    user_id: int, health_sleep: health_sleep_schema.HealthSleep, db: Session
) -> health_sleep_schema.HealthSleep:
    """
    Create a new health sleep record for a user.

    Args:
        user_id (int): The ID of the user for whom the health sleep record is being created.
        health_sleep (health_sleep_schema.HealthSleep): The health sleep data to be created.
        db (Session): The database session object.

    Returns:
        health_sleep_schema.HealthSleep: The created health sleep record with the assigned ID.

    Raises:
        HTTPException:
            - 409 Conflict: If a duplicate entry exists for the given date.
            - 500 Internal Server Error: If any other error occurs during the creation process.

    Notes:
        - If the date is None, it will be automatically set to the current date.
        - The function commits the transaction and refreshes the object to get the assigned ID.
        - In case of errors, the transaction is rolled back before raising the exception.
    """
    try:
        # Check if date is None
        if health_sleep.date is None:
            # Set the date to the current date
            health_sleep.date = func.now()

        # Create a new health_sleep
        db_health_sleep = health_sleep_models.HealthSleep(
            **health_sleep.model_dump(
                exclude={"id", "user_id"}, exclude_none=False, mode="json"
            ),
            user_id=user_id,
        )

        # Add the health_sleep to the database
        db.add(db_health_sleep)
        db.commit()
        db.refresh(db_health_sleep)

        # Set the id of the health_sleep
        health_sleep.id = db_health_sleep.id

        # Return the health_sleep
        return health_sleep
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate entry error. Check if there is already a entry created for {health_sleep.date}",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_health_sleep: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_health_sleep(
    user_id, health_sleep: health_sleep_schema.HealthSleep, db: Session
) -> health_sleep_schema.HealthSleep:
    """
    Edit an existing health sleep record for a user.

    This function updates a health sleep record in the database for a specific user.
    It retrieves the existing record, updates only the fields that are provided,
    and commits the changes to the database.

    Args:
        user_id: The ID of the user whose health sleep record is being edited.
        health_sleep (health_sleep_schema.HealthSleep): The health sleep schema object
            containing the updated data. Only fields that are set will be updated.
        db (Session): The database session object for executing queries.

    Returns:
        health_sleep_schema.HealthSleep: The updated health sleep schema object.

    Raises:
        HTTPException:
            - 404 NOT_FOUND if the health sleep record is not found for the given
              user_id and health_sleep.id.
            - 500 INTERNAL_SERVER_ERROR if any other error occurs during the
              update process.

    Note:
        The function performs a partial update, only modifying fields that are
        explicitly set in the input health_sleep object. The database transaction
        is rolled back if any error occurs during the update.
    """
    try:
        # Get the health_sleep from the database
        db_health_sleep = (
            db.query(health_sleep_models.HealthSleep)
            .filter(
                health_sleep_models.HealthSleep.id == health_sleep.id,
                health_sleep_models.HealthSleep.user_id == user_id,
            )
            .first()
        )

        if db_health_sleep is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Health sleep not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Dictionary of the fields to update if they are not None
        health_sleep_data = health_sleep.model_dump(exclude_unset=True, mode="json")
        # Iterate over the fields and update the db_health_sleep dynamically
        for key, value in health_sleep_data.items():
            setattr(db_health_sleep, key, value)

        # Commit the transaction
        db.commit()

        return health_sleep
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in edit_health_sleep: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_health_sleep(user_id: int, health_sleep_id: int, db: Session) -> None:
    """
    Delete a health sleep record for a specific user.

    This function deletes a health sleep entry from the database based on the provided
    health_sleep_id and user_id. It ensures that the record belongs to the specified user
    before deletion.

    Args:
        user_id (int): The ID of the user who owns the health sleep record.
        health_sleep_id (int): The ID of the health sleep record to delete.
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
        # Delete the health_sleep
        num_deleted = (
            db.query(health_sleep_models.HealthSleep)
            .filter(
                health_sleep_models.HealthSleep.id == health_sleep_id,
                health_sleep_models.HealthSleep.user_id == user_id,
            )
            .delete()
        )

        # Check if the health_sleep was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Health sleep with id {health_sleep_id} for user {user_id} not found",
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
            f"Error in delete_health_sleep: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
