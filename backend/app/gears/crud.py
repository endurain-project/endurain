import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from urllib.parse import unquote

import models

import gears.schema as gears_schema
import gears.utils as gears_utils


# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def get_gear_user_by_id(gear_id: int, db: Session) -> gears_schema.Gear | None:
    try:
        gear = db.query(models.Gear).filter(models.Gear.id == gear_id).first()

        # Check if gear is None and return None if it is
        if gear is None:
            return None

        gear.created_at = gear.created_at.strftime("%Y-%m-%d %H:%M:%S")

        # Return the gear
        return gear
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_gear_user_by_id: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_users_with_pagination(
    user_id: int, db: Session, page_number: int = 1, num_records: int = 5
) -> list[gears_schema.Gear] | None:
    try:
        # Get the gear by user ID from the database
        gear = (
            db.query(models.Gear)
            .filter(models.Gear.user_id == user_id)
            .order_by(models.Gear.nickname.asc())
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )

        # Check if gear is None and return None if it is
        if gear is None:
            return None

        # Format the created_at date
        for g in gear:
            g.created_at = g.created_at.strftime("%Y-%m-%d %H:%M:%S")

        # Return the gear
        return gear
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_gear_users_with_pagination: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_user(user_id: int, db: Session) -> list[gears_schema.Gear] | None:
    try:
        # Get the gear by user ID from the database
        gears = db.query(models.Gear).filter(models.Gear.user_id == user_id).all()

        # Check if gear is None and return None if it is
        if gears is None:
            return None

        # Format the created_at date
        for g in gears:
            g.created_at = g.created_at.strftime("%Y-%m-%d %H:%M:%S")

        # Return the gear
        return gears
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_gear_user: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_user_by_nickname(
    user_id: int, nickname: str, db: Session
) -> list[gears_schema.Gear] | None:
    try:
        # Unquote the nickname and change "+" to whitespace
        parsed_nickname = unquote(nickname).replace("+", " ")

        # Get the gear by user ID and nickname from the database
        gears = (
            db.query(models.Gear)
            .filter(
                models.Gear.nickname.like(f"%{parsed_nickname}%"),
                models.Gear.user_id == user_id,
            )
            .all()
        )

        # Check if gear is None and return None if it is
        if gears is None:
            return None

        # Format the created_at date
        for g in gears:
            g.created_at = g.created_at.strftime("%Y-%m-%d %H:%M:%S")

        # return the gear
        return gears
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_gear_user_by_nickname: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_by_type_and_user(gear_type: int, user_id: int, db: Session):
    try:
        # Get the gear by type from the database
        gear = (
            db.query(models.Gear)
            .filter(models.Gear.gear_type == gear_type, models.Gear.user_id == user_id)
            .order_by(models.Gear.nickname)
            .all()
        )

        # Check if gear is None and return None if it is
        if gear is None:
            return None

        # Format the created_at date
        for g in gear:
            g.created_at = g.created_at.strftime("%Y-%m-%d %H:%M:%S")

        # Return the gear
        return gear
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_gear_by_type_and_user: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_by_strava_id_from_user_id(
    gear_strava_id: str, user_id: int, db: Session
) -> gears_schema.Gear | None:
    try:
        # Get the gear from the database
        gear = (
            db.query(models.Gear)
            .filter(
                models.Gear.user_id == user_id,
                models.Gear.strava_gear_id == gear_strava_id,
            )
            .first()
        )

        # Check if there is gear
        if not gear:
            return None

        gear.created_at = gear.created_at.strftime("%Y-%m-%d %H:%M:%S")

        # Return gear
        return gear

    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_activity_by_id_from_user_id: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_multiple_gears(gears: list[gears_schema.Gear], user_id: int, db: Session):
    try:
        # Filter out None values from the gears list
        valid_gears = [gear for gear in gears if gear is not None]

        # Create a list of gear objects
        new_gears = [
            gears_utils.transform_schema_gear_to_model_gear(gear, user_id)
            for gear in valid_gears
        ]

        # Add the gears to the database
        db.add_all(new_gears)
        db.commit()

    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if nickname or strava_gear_id are unique",
        ) from integrity_error

    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(f"Error in create_multiple_gears: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_gear(gear: gears_schema.Gear, user_id: int, db: Session):
    try:
        new_gear = gears_utils.transform_schema_gear_to_model_gear(gear, user_id)

        # Add the gear to the database
        db.add(new_gear)
        db.commit()
        db.refresh(new_gear)

        # Return the gear
        return new_gear
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if nickname or strava_gear_id are unique",
        ) from integrity_error

    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(f"Error in create_gear: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_gear(gear_id: int, gear: gears_schema.Gear, db: Session):
    try:
        # Get the gear from the database
        db_gear = db.query(models.Gear).filter(models.Gear.id == gear_id).first()

        # Update the gear
        if gear.brand is not None:
            db_gear.brand = unquote(gear.brand).replace("+", " ")
        if gear.model is not None:
            db_gear.model = unquote(gear.model).replace("+", " ")
        if gear.nickname is not None:
            db_gear.nickname = unquote(gear.nickname).replace("+", " ")
        if gear.gear_type is not None:
            db_gear.gear_type = gear.gear_type
        if gear.created_at is not None:
            db_gear.created_at = gear.created_at
        if gear.is_active is not None:
            print(f"Gear is active value: {gear.is_active}")
            db_gear.is_active = gear.is_active
        if gear.strava_gear_id is not None:
            db_gear.strava_gear_id = gear.strava_gear_id

        # Commit the transaction
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(f"Error in edit_gear: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_gear(gear_id: int, db: Session):
    try:
        # Delete the gear
        num_deleted = db.query(models.Gear).filter(models.Gear.id == gear_id).delete()

        # Check if the gear was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Gear with id {gear_id} not found",
            )

        # Commit the transaction
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(f"Error in delete_gear: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_all_strava_gear_for_user(user_id: int, db: Session):
    try:
        # Delete the gear records with strava_gear_id not null for the user
        num_deleted = (
            db.query(models.Gear)
            .filter(
                models.Gear.user_id == user_id, models.Gear.strava_gear_id.isnot(None)
            )
            .delete()
        )

        # Check if any records were deleted and commit the transaction
        if num_deleted != 0:
            # Commit the transaction
            db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(f"Error in delete_all_strava_gear_for_user: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
