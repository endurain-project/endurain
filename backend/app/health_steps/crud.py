from fastapi import HTTPException, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import health_steps.schema as health_steps_schema
import health_steps.models as health_steps_models

import core.logger as core_logger


def get_health_steps_number(user_id: int, db: Session):
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


def get_all_health_steps_by_user_id(user_id: int, db: Session):
    try:
        # Get the health_steps from the database
        health_steps = (
            db.query(health_steps_models.HealthSteps)
            .filter(health_steps_models.HealthSteps.user_id == user_id)
            .order_by(desc(health_steps_models.HealthSteps.date))
            .all()
        )

        # Check if there are health_steps if not return None
        if not health_steps:
            return None

        # Return the health_steps
        return health_steps
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
):
    try:
        # Get the health_steps from the database
        health_steps = (
            db.query(health_steps_models.HealthSteps)
            .filter(health_steps_models.HealthSteps.user_id == user_id)
            .order_by(desc(health_steps_models.HealthSteps.date))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )

        # Check if there are health_steps if not return None
        if not health_steps:
            return None

        # Return the health_steps
        return health_steps
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


def get_health_steps_by_date(user_id: int, date: str, db: Session):
    try:
        # Get the health_steps from the database
        health_steps = (
            db.query(health_steps_models.HealthSteps)
            .filter(
                health_steps_models.HealthSteps.date == date,
                health_steps_models.HealthSteps.user_id == user_id,
            )
            .first()
        )

        # Check if there are health_steps if not return None
        if not health_steps:
            return None

        # Return the health_steps
        return health_steps
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
):
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
):
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


def delete_health_steps(user_id: int, health_steps_id: int, db: Session):
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
