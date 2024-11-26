from fastapi import HTTPException, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import users.crud as users_crud

import health_data.schema as health_data_schema
import health_data.models as health_data_models

import core.logger as core_logger


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
        core_logger.print_to_log(f"Error in get_health_data_number: {err}", "error")
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_data(user_id: int, db: Session):
    try:
        # Get the health_data from the database
        health_data = (
            db.query(health_data_models.HealthData)
            .filter(health_data_models.HealthData.user_id == user_id)
            .order_by(desc(health_data_models.HealthData.created_at))
            .all()
        )

        # Check if there are health_data if not return None
        if not health_data:
            return None

        # Return the health_data
        return health_data
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_health_data: {err}", "error")
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
            .order_by(desc(health_data_models.HealthData.created_at))
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
            f"Error in get_health_data_with_pagination: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_health_data_by_created_at(user_id: int, created_at: str, db: Session):
    try:
        # Get the health_data from the database
        health_data = (
            db.query(health_data_models.HealthData)
            .filter(
                health_data_models.HealthData.created_at == created_at,
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
            f"Error in get_health_data_by_created_at: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_health_data(
    health_data: health_data_schema.HealthData, user_id: int, db: Session
):
    try:
        # Check if bmi is None
        if health_data.bmi is None:
            # Get the user from the database
            user = users_crud.get_user_by_id(user_id, db)

            # Check if user is not None
            if user is not None:
                # Calculate the bmi
                health_data.bmi = health_data.weight / ((user.height / 100) ** 2)

        # Create a new health_data
        db_health_data = health_data_models.HealthData(
            user_id=user_id,
            created_at=func.now(),
            weight=health_data.weight,
            bmi=health_data.bmi,
            body_fat=health_data.body_fat,
            body_water=health_data.body_water,
            bone_mass=health_data.bone_mass,
            muscle_mass=health_data.muscle_mass,
            physique_rating=health_data.physique_rating,
            visceral_fat=health_data.visceral_fat,
            metabolic_age=health_data.metabolic_age,
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
        core_logger.print_to_log(f"Error in create_health_data: {err}", "error")
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_health_weight_data(
    health_data: health_data_schema.HealthData, user_id: int, db: Session
):
    try:
        # Create a new health_data
        db_health_data = health_data_models.HealthData(
            user_id=user_id,
            created_at=health_data.created_at,
            weight=health_data.weight,
        )

        # Add the health_data to the database
        db.add(db_health_data)
        db.commit()
        db.refresh(db_health_data)

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
        core_logger.print_to_log(f"Error in create_health_weight_data: {err}", "error")
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_health_weight_data(health_data: health_data_schema.HealthData, db: Session):
    try:
        # Get the health_data from the database
        db_health_data = (
            db.query(health_data_models.HealthData)
            .filter(health_data_models.HealthData.id == health_data.id)
            .first()
        )

        if db_health_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Health data not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Update the user
        if health_data.created_at is not None:
            db_health_data.created_at = health_data.created_at
        if health_data.weight is not None:
            db_health_data.weight = health_data.weight

        # Commit the transaction
        db.commit()
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if date selected is not already added",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in edit_health_weight_data: {err}", "error")

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_health_weight_data(health_data_id: int, user_id: int, db: Session):
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

        # Check if the gear was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Health data with id {health_data_id} for user {user_id} not found",
            )

        # Commit the transaction
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in delete_health_weight_data: {err}", "error")

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
