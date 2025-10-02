from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from urllib.parse import unquote

import gears.gear.schema as gears_schema
import gears.gear.utils as gears_utils
import gears.gear.models as gears_models

import core.logger as core_logger


def get_gear_user_by_id(
    user_id: int, gear_id: int, db: Session
) -> gears_schema.Gear | None:
    try:
        gear = (
            db.query(gears_models.Gear)
            .filter(
                gears_models.Gear.user_id == user_id, gears_models.Gear.id == gear_id
            )
            .first()
        )

        # Check if gear is None and return None if it is
        if gear is None:
            return None

        gear = gears_utils.serialize_gear(gear)

        # Return the gear
        return gear
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_gear_user_by_id: {err}", "error", exc=err
        )
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
        gears = (
            db.query(gears_models.Gear)
            .filter(gears_models.Gear.user_id == user_id)
            .order_by(gears_models.Gear.nickname.asc())
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )

        # Check if gear is None and return None if it is
        if gears is None:
            return None

        # Format the created_at date
        for g in gears:
            g = gears_utils.serialize_gear(g)

        # Return the gear
        return gears
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_gear_users_with_pagination: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_user(user_id: int, db: Session) -> list[gears_schema.Gear] | None:
    try:
        # Get the gear by user ID from the database
        gears = (
            db.query(gears_models.Gear)
            .filter(gears_models.Gear.user_id == user_id)
            .all()
        )

        # Check if gear is None and return None if it is
        if gears is None:
            return None

        # Format the created_at date
        for g in gears:
            g = gears_utils.serialize_gear(g)

        # Return the gear
        return gears
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_gear_user: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_user_contains_nickname(
    user_id: int, nickname: str, db: Session
) -> list[gears_schema.Gear] | None:
    try:
        # Unquote the nickname and change "+" to whitespace
        parsed_nickname = unquote(nickname).replace("+", " ").lower()

        # Get the gear by user ID and nickname from the database
        gears = (
            db.query(gears_models.Gear)
            .filter(
                func.lower(gears_models.Gear.nickname).like(f"%{parsed_nickname}%"),
                gears_models.Gear.user_id == user_id,
            )
            .all()
        )

        # Check if gear is None and return None if it is
        if gears is None:
            return None

        # Format the created_at date
        for g in gears:
            g = gears_utils.serialize_gear(g)

        # return the gear
        return gears
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_gear_user_contains_nickname: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_user_by_nickname(
    user_id: int, nickname: str, db: Session
) -> gears_schema.Gear | None:
    try:
        # Unquote the nickname and change "+" to whitespace
        parsed_nickname = unquote(nickname).replace("+", " ").lower()

        # Get the gear by user ID and nickname from the database
        gear = (
            db.query(gears_models.Gear)
            .filter(
                func.lower(gears_models.Gear.nickname) == parsed_nickname,
                gears_models.Gear.user_id == user_id,
            )
            .first()
        )

        # Check if gear is None and return None if it is
        if gear is None:
            return None

        # Serialize the gear
        gear_serialized = gears_utils.serialize_gear(gear)

        # return the gear
        return gear_serialized
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_gear_user_by_nickname: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_by_type_and_user(gear_type: int, user_id: int, db: Session):
    try:
        # Get the gear by type from the database
        gear = (
            db.query(gears_models.Gear)
            .filter(
                gears_models.Gear.gear_type == gear_type,
                gears_models.Gear.user_id == user_id,
            )
            .order_by(gears_models.Gear.nickname)
            .all()
        )

        # Check if gear is None and return None if it is
        if gear is None:
            return None

        # Format the created_at date
        for g in gear:
            g = gears_utils.serialize_gear(g)

        # Return the gear
        return gear
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_gear_by_type_and_user: {err}", "error", exc=err
        )
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
            db.query(gears_models.Gear)
            .filter(
                gears_models.Gear.user_id == user_id,
                gears_models.Gear.strava_gear_id == gear_strava_id,
            )
            .first()
        )

        # Check if there is gear
        if not gear:
            return None

        gear = gears_utils.serialize_gear(gear)

        # Return gear
        return gear

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_gear_by_strava_id_from_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_by_garminconnect_id_from_user_id(
    gear_garminconnect_id: str, user_id: int, db: Session
) -> gears_schema.Gear | None:
    try:
        # Get the gear from the database
        gear = (
            db.query(gears_models.Gear)
            .filter(
                gears_models.Gear.user_id == user_id,
                gears_models.Gear.garminconnect_gear_id == gear_garminconnect_id,
            )
            .first()
        )

        # Check if there is gear
        if not gear:
            return None

        gear = gears_utils.serialize_gear(gear)

        # Return gear
        return gear

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_gear_by_garminconnect_id_from_user_id: {err}",
            "error",
            exc=err,
        )
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
            detail="Duplicate entry error. Check if nickname, strava_gear_id or garminconnect_gear_id are unique",
        ) from integrity_error

    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_multiple_gears: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_gear(gear: gears_schema.Gear, user_id: int, db: Session):
    try:
        gear_check = get_gear_user_by_nickname(
            user_id, gear.nickname, db
        )

        if gear_check is not None:
            # If the gear already exists, raise an HTTPException with a 409 Conflict status code
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Gear with nickname {gear.nickname} already exists for user {user_id}",
            )

        new_gear = gears_utils.transform_schema_gear_to_model_gear(gear, user_id)

        # Add the gear to the database
        db.add(new_gear)
        db.commit()
        db.refresh(new_gear)

        gear_serialized = gears_utils.serialize_gear(new_gear)

        # Return the gear
        return gear_serialized
    except HTTPException as http_err:
        # If an HTTPException is raised, re-raise it
        raise http_err
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate entry error. Check if strava_gear_id or garminconnect_gear_id are unique",
        ) from integrity_error
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in create_gear: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_gear(gear_id: int, gear: gears_schema.Gear, db: Session):
    try:
        # Get the gear from the database
        db_gear = (
            db.query(gears_models.Gear).filter(gears_models.Gear.id == gear_id).first()
        )

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
            db_gear.is_active = gear.is_active
        if gear.initial_kms is not None:
            db_gear.initial_kms = gear.initial_kms
        if gear.purchase_value is not None:
            db_gear.purchase_value = gear.purchase_value
        if gear.strava_gear_id is not None:
            db_gear.strava_gear_id = gear.strava_gear_id
        if gear.garminconnect_gear_id is not None:
            db_gear.garminconnect_gear_id = gear.garminconnect_gear_id

        # Commit the transaction
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in edit_gear: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_gear(gear_id: int, db: Session):
    try:
        # Delete the gear
        num_deleted = (
            db.query(gears_models.Gear).filter(gears_models.Gear.id == gear_id).delete()
        )

        # Check if the gear was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Gear with id {gear_id} not found",
            )

        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in delete_gear: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_all_strava_gear_for_user(user_id: int, db: Session):
    try:
        # Delete the gear records with strava_gear_id not null for the user
        num_deleted = (
            db.query(gears_models.Gear)
            .filter(
                gears_models.Gear.user_id == user_id,
                gears_models.Gear.strava_gear_id.isnot(None),
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
        core_logger.print_to_log(
            f"Error in delete_all_strava_gear_for_user: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_all_garminconnect_gear_for_user(user_id: int, db: Session):
    try:
        # Delete the gear records with garminconnect_gear_id not null for the user
        num_deleted = (
            db.query(gears_models.Gear)
            .filter(
                gears_models.Gear.user_id == user_id,
                gears_models.Gear.garminconnect_gear_id.isnot(None),
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
        core_logger.print_to_log(
            f"Error in delete_all_garminconnect_gear_for_user: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
