from fastapi import HTTPException, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import health_sleep.schema as health_sleep_schema
import health_sleep.models as health_sleep_models

import core.logger as core_logger


def get_health_sleep_number(user_id: int, db: Session):
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


def get_all_health_sleep_by_user_id(user_id: int, db: Session):
    try:
        # Get the health_sleep from the database
        health_sleep = (
            db.query(health_sleep_models.HealthSleep)
            .filter(health_sleep_models.HealthSleep.user_id == user_id)
            .order_by(desc(health_sleep_models.HealthSleep.date))
            .all()
        )

        # Check if there are health_sleep if not return None
        if not health_sleep:
            return None

        # Return the health_sleep
        return health_sleep
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
):
    try:
        # Get the health_sleep from the database
        health_sleep = (
            db.query(health_sleep_models.HealthSleep)
            .filter(health_sleep_models.HealthSleep.user_id == user_id)
            .order_by(desc(health_sleep_models.HealthSleep.date))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )

        # Check if there are health_sleep if not return None
        if not health_sleep:
            return None

        # Return the health_sleep
        return health_sleep
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


def get_health_sleep_by_date(user_id: int, date: str, db: Session):
    try:
        # Get the health_sleep from the database
        health_sleep = (
            db.query(health_sleep_models.HealthSleep)
            .filter(
                health_sleep_models.HealthSleep.date == date,
                health_sleep_models.HealthSleep.user_id == user_id,
            )
            .first()
        )

        # Check if there are health_sleep if not return None
        if not health_sleep:
            return None

        # Return the health_sleep
        return health_sleep
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
):
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
):
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
