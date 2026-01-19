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
    """
    Retrieve a list of gear objects for a given user where the gear's nickname contains the specified substring.

    Args:
        user_id (int): The ID of the user whose gear is being queried.
        nickname (str): The substring to search for within gear nicknames. URL-encoded strings are supported.
        db (Session): The SQLAlchemy database session.

    Returns:
        list[gears_schema.Gear] | None: A list of gear objects matching the criteria, or None if no gear is found.

    Raises:
        HTTPException: If an unexpected error occurs during the database query or processing.
    """
    try:
        # Unquote the nickname and change "+" to whitespace
        parsed_nickname = unquote(nickname).replace("+", " ").lower().strip()

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
    """
    Retrieve a gear belonging to a user by its nickname.

    This function attempts to find a gear in the database that matches the given user ID and nickname.
    The nickname is URL-decoded, "+" characters are replaced with spaces, and the result is lowercased and stripped of whitespace before querying.
    If a matching gear is found, it is serialized and returned; otherwise, None is returned.
    In case of any exception, an error is logged and an HTTP 500 Internal Server Error is raised.

    Args:
        user_id (int): The ID of the user who owns the gear.
        nickname (str): The nickname of the gear to retrieve.
        db (Session): The SQLAlchemy database session.

    Returns:
        gears_schema.Gear | None: The serialized gear object if found, otherwise None.

    Raises:
        HTTPException: If an internal server error occurs during the process.
    """
    try:
        # Unquote the nickname and change "+" to whitespace
        parsed_nickname = unquote(nickname).replace("+", " ").lower().strip()

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
        # 1) Filter out None and gears without a usable nickname
        valid_gears = [
            gear
            for gear in (gears or [])
            if gear is not None
            and getattr(gear, "nickname", None)
            and str(gear.nickname).replace("+", " ").strip()
        ]

        # 2) De-dupe within the valid_gears payload (case-insensitive, trimmed)
        seen = set()
        deduped: list[gears_schema.Gear] = []
        for gear in valid_gears:
            nickname_normalized = str(gear.nickname).replace("+", " ").lower().strip()
            if nickname_normalized not in seen:
                seen.add(nickname_normalized)
                deduped.append(gear)
            else:
                core_logger.print_to_log_and_console(
                    f"Duplicate nickname '{gear.nickname}' in request for user {user_id}, skipping",
                    "warning",
                )

        # 3) Skip any that already exist for this user
        gears_to_create: list[gears_schema.Gear] = []
        for gear in deduped:
            gear_check = get_gear_user_by_nickname(user_id, gear.nickname, db)
            if gear_check is not None:
                core_logger.print_to_log_and_console(
                    f"Gear with nickname '{gear.nickname}' already exists for user {user_id}, skipping",
                    "warning",
                )
            else:
                gears_to_create.append(gear)

        # 4) Persist any remaining
        if gears_to_create:
            new_gears = [
                gears_utils.transform_schema_gear_to_model_gear(gear, user_id)
                for gear in gears_to_create
            ]
            db.add_all(new_gears)
            db.commit()

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
        gear_check = get_gear_user_by_nickname(user_id, gear.nickname, db)

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
        if gear.active is not None:
            db_gear.active = gear.active
        if gear.initial_kms is not None:
            db_gear.initial_kms = gear.initial_kms
        if gear.purchase_value is not None:
            db_gear.purchase_value = gear.purchase_value
        if gear.strava_gear_id is not None:
            db_gear.strava_gear_id = gear.strava_gear_id
        if gear.garminconnect_gear_id is not None:
            db_gear.garminconnect_gear_id = gear.garminconnect_gear_id
        if gear.serial_number is not None:
            db_gear.serial_number = gear.serial_number
        if gear.computer_model_id is not None:
            db_gear.computer_model_id = gear.computer_model_id

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


def get_watch_gear_by_serial_number(
    user_id: int, serial_number: str, db: Session
) -> gears_schema.Gear | None:
    """
    Find watch/computer gear (type 9) for a user by serial number.

    Args:
        user_id: The user ID
        serial_number: The device serial number
        db: Database session

    Returns:
        The gear if found, None otherwise
    """
    try:
        gear = (
            db.query(gears_models.Gear)
            .filter(
                gears_models.Gear.user_id == user_id,
                gears_models.Gear.gear_type == 9,
                gears_models.Gear.serial_number == serial_number,
            )
            .first()
        )

        if gear is None:
            return None

        return gears_utils.serialize_gear(gear)
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_watch_gear_by_serial_number: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_watch_gear_by_model_name(
    user_id: int, model_name: str, db: Session
) -> gears_schema.Gear | None:
    """
    Find watch/computer gear (type 9) for a user by model name.
    Used for devices without serial numbers (e.g., Suunto).

    Args:
        user_id: The user ID
        model_name: The device model name
        db: Database session

    Returns:
        The gear if found, None otherwise
    """
    try:
        gear = (
            db.query(gears_models.Gear)
            .filter(
                gears_models.Gear.user_id == user_id,
                gears_models.Gear.gear_type == 9,
                gears_models.Gear.model == model_name,
                gears_models.Gear.serial_number.is_(None),
            )
            .first()
        )

        if gear is None:
            return None

        return gears_utils.serialize_gear(gear)
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_watch_gear_by_model_name: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_or_create_watch_gear_from_fit_data(
    user_id: int,
    serial_number: str | None,
    computer_model_id: int | None,
    model_name: str | None,
    manufacturer: str | None,
    db: Session,
) -> gears_schema.Gear | None:
    """
    Find or create watch/computer gear based on FIT file device info.

    If a watch gear with the same serial number exists for the user, return it.
    For devices without serial numbers (e.g., Suunto), uses model_name as identifier.
    Otherwise, create a new watch gear entry.

    Args:
        user_id: The user ID
        serial_number: Device serial number from FIT file
        computer_model_id: ID from computer_models table (if matched)
        model_name: Device model name
        manufacturer: Device manufacturer
        db: Database session

    Returns:
        The existing or newly created gear, or None if no identifier available
    """
    try:
        # Try to find existing gear by serial number first
        if serial_number:
            existing_gear = get_watch_gear_by_serial_number(user_id, serial_number, db)
            if existing_gear:
                return existing_gear
        # For devices without serial numbers, try to find by model name
        elif model_name:
            existing_gear = get_watch_gear_by_model_name(user_id, model_name, db)
            if existing_gear:
                return existing_gear

        # Need at least serial_number or model_name to create gear
        if not serial_number and not model_name:
            return None

        # Create a nickname based on the model name or manufacturer
        if model_name:
            nickname = model_name
        elif manufacturer:
            nickname = f"{manufacturer} Watch"
        else:
            nickname = "Unknown Watch"

        # Check if nickname already exists and make it unique
        nickname_check = get_gear_user_by_nickname(user_id, nickname, db)
        if nickname_check and serial_number:
            # Append serial number suffix to make nickname unique
            nickname = f"{nickname} ({serial_number[-4:]})"

        # Create new watch gear
        new_gear = gears_schema.Gear(
            nickname=nickname,
            brand=manufacturer.title() if manufacturer else None,
            model=model_name,
            gear_type=9,  # Watch/Computer
            active=True,
            serial_number=serial_number,
            computer_model_id=computer_model_id,
        )

        created_gear = gears_utils.transform_schema_gear_to_model_gear(new_gear, user_id)
        db.add(created_gear)
        db.commit()
        db.refresh(created_gear)

        identifier = serial_number if serial_number else f"model: {model_name}"
        core_logger.print_to_log_and_console(
            f"Auto-created watch gear '{nickname}' for user {user_id} ({identifier})"
        )

        return gears_utils.serialize_gear(created_gear)
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in get_or_create_watch_gear_from_fit_data: {err}", "error", exc=err
        )
        # Don't raise - just return None to not block activity import
        return None
