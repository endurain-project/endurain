from fastapi import HTTPException, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import users.user.crud as users_crud

import health_data.schema as health_data_schema
import health_data.models as health_data_models
import health_data.utils as health_data_utils

import core.logger as core_logger


def get_all_health_data(db: Session):
    try:
        # Get the health_data from the database
        health_data = (
            db.query(health_data_models.HealthData)
            .order_by(desc(health_data_models.HealthData.date))
            .all()
        )

        # Check if there are health_data if not return None
        if not health_data:
            return None

        # Return the health_data
        return health_data
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_health_data: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_data_number(user_id: int, db: Session):
    try:
        # Get the number of health_data from the database
        return (
            db.query(health_data_models.HealthData)
            .filter(health_data_models.HealthData.user_id == user_id)
            .count()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_data_number: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_health_data_by_user_id(user_id: int, db: Session):
    try:
        # Get the health_data from the database
        health_data = (
            db.query(health_data_models.HealthData)
            .filter(health_data_models.HealthData.user_id == user_id)
            .order_by(desc(health_data_models.HealthData.date))
            .all()
        )

        # Check if there are health_data if not return None
        if not health_data:
            return None

        # Return the health_data
        return health_data
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_health_data_by_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_data_with_pagination(
    user_id: int, db: Session, page_number: int = 1, num_records: int = 5
):
    try:
        # Get the health_data from the database
        health_data = (
            db.query(health_data_models.HealthData)
            .filter(health_data_models.HealthData.user_id == user_id)
            .order_by(desc(health_data_models.HealthData.date))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )

        # Check if there are health_data if not return None
        if not health_data:
            return None

        # Return the health_data
        return health_data
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_data_with_pagination: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_data_by_date(user_id: int, date: str, db: Session):
    try:
        # Get the health_data from the database
        health_data = (
            db.query(health_data_models.HealthData)
            .filter(
                health_data_models.HealthData.date == date,
                health_data_models.HealthData.user_id == user_id,
            )
            .first()
        )

        # Check if there are health_data if not return None
        if not health_data:
            return None

        # Return the health_data
        return health_data
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_health_data_by_date: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_health_data(
    user_id: int, health_data: health_data_schema.HealthData, db: Session
):
    try:
        # Check if date is None
        if health_data.date is None:
            # Set the date to the current date
            health_data.date = func.now()

        # Check if bmi is None
        if health_data.bmi is None:
            health_data = health_data_utils.calculate_bmi(health_data, user_id, db)

        # Create a new health_data
        db_health_data = health_data_models.HealthData(
            user_id=user_id,
            date=health_data.date,
            weight=health_data.weight,
            bmi=health_data.bmi,
            # body_fat=health_data.body_fat,
            # body_water=health_data.body_water,
            # bone_mass=health_data.bone_mass,
            # muscle_mass=health_data.muscle_mass,
            # physique_rating=health_data.physique_rating,
            # visceral_fat=health_data.visceral_fat,
            # metabolic_age=health_data.metabolic_age,
            garminconnect_body_composition_id=health_data.garminconnect_body_composition_id,
        )

        # Add the health_data to the database
        db.add(db_health_data)
        db.commit()
        db.refresh(db_health_data)

        # Set the id of the health_data
        health_data.id = db_health_data.id

        # Return the health_data
        return health_data
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if there is already a entry created for today",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_health_data: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_health_data(user_id, health_data: health_data_schema.HealthData, db: Session):
    try:
        # Get the health_data from the database
        db_health_data = (
            db.query(health_data_models.HealthData)
            .filter(
                health_data_models.HealthData.id == health_data.id,
                health_data_models.HealthData.user_id == user_id,
            )
            .first()
        )

        if db_health_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Health data not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if bmi is None
        if health_data.bmi is None and health_data.weight is not None:
            health_data = health_data_utils.calculate_bmi(health_data, user_id, db)

        # Dictionary of the fields to update if they are not None
        health_data_data = health_data.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_health_data dynamically
        for key, value in health_data_data.items():
            setattr(db_health_data, key, value)

        # Commit the transaction
        db.commit()

        return health_data
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in edit_health_data: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_health_data(user_id: int, health_data_id: int, db: Session):
    try:
        # Delete the gear
        num_deleted = (
            db.query(health_data_models.HealthData)
            .filter(
                health_data_models.HealthData.id == health_data_id,
                health_data_models.HealthData.user_id == user_id,
            )
            .delete()
        )

        # Check if the health_data was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Health data with id {health_data_id} for user {user_id} not found",
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
            f"Error in delete_health_weight_data: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
