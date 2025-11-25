from fastapi import HTTPException, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import health_weight.schema as health_weight_schema
import health_weight.models as health_weight_models
import health_weight.utils as health_weight_utils

import core.logger as core_logger


def get_all_health_weight(db: Session):
    try:
        # Get the health_weight from the database
        health_weight = (
            db.query(health_weight_models.HealthWeight)
            .order_by(desc(health_weight_models.HealthWeight.date))
            .all()
        )

        # Check if there are health_weight if not return None
        if not health_weight:
            return None

        # Return the health_weight
        return health_weight
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


def get_health_weight_number(user_id: int, db: Session):
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


def get_all_health_weight_by_user_id(user_id: int, db: Session):
    try:
        # Get the health_weight from the database
        health_weight = (
            db.query(health_weight_models.HealthWeight)
            .filter(health_weight_models.HealthWeight.user_id == user_id)
            .order_by(desc(health_weight_models.HealthWeight.date))
            .all()
        )

        # Check if there are health_weight if not return None
        if not health_weight:
            return None

        # Return the health_weight
        return health_weight
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
):
    try:
        # Get the health_weight from the database
        health_weight = (
            db.query(health_weight_models.HealthWeight)
            .filter(health_weight_models.HealthWeight.user_id == user_id)
            .order_by(desc(health_weight_models.HealthWeight.date))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )

        # Check if there are health_weight if not return None
        if not health_weight:
            return None

        # Return the health_weight
        return health_weight
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


def get_health_weight_by_date(user_id: int, date: str, db: Session):
    try:
        # Get the health_weight from the database
        health_weight = (
            db.query(health_weight_models.HealthWeight)
            .filter(
                health_weight_models.HealthWeight.date == date,
                health_weight_models.HealthWeight.user_id == user_id,
            )
            .first()
        )

        # Check if there are health_weight if not return None
        if not health_weight:
            return None

        # Return the health_weight
        return health_weight
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
):
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
):
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


def delete_health_weight(user_id: int, health_weight_id: int, db: Session):
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
