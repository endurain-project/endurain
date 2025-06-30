from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

import users.user_integrations.schema as user_integrations_schema
import users.user_integrations.models as user_integrations_models

import core.cryptography as core_cryptography
import core.logger as core_logger


def get_user_integrations_by_user_id(user_id: int, db: Session):
    try:
        # Get the user integrations by the user id
        user_integrations = (
            db.query(user_integrations_models.UsersIntegrations)
            .filter(user_integrations_models.UsersIntegrations.user_id == user_id)
            .first()
        )

        # Check if user_integrations is None and return None if it is
        if user_integrations is None:
            # If the user was not found, return a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Return the user integrations
        return user_integrations
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_integrations_by_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_integrations_by_strava_state(strava_state: str, db: Session):
    try:
        # Get user integrations based on the strava state
        user_integrations = (
            db.query(user_integrations_models.UsersIntegrations)
            .filter(
                user_integrations_models.UsersIntegrations.strava_state == strava_state
            )
            .first()
        )

        # Check if user_integrations is None and return None if it is
        if user_integrations is None:
            return None

        # Return the user integrations
        return user_integrations
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_integrations_by_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_user_integrations(user_id: int, db: Session):
    try:
        # Create a new user integrations
        user_integrations = user_integrations_models.UsersIntegrations(
            user_id=user_id,
            strava_sync_gear=False,
            garminconnect_sync_gear=False,
        )

        # Add the user integrations to the database
        db.add(user_integrations)
        db.commit()
        db.refresh(user_integrations)

        # Return the user integrations
        return user_integrations
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_user_integrations: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def link_strava_account(
    user_integrations: user_integrations_schema.UsersIntegrations,
    tokens: dict,
    db: Session,
):
    try:
        # Update the user integrations with the tokens
        user_integrations.strava_token = core_cryptography.encrypt_token_fernet(
            tokens["access_token"]
        )
        user_integrations.strava_refresh_token = core_cryptography.encrypt_token_fernet(
            tokens["refresh_token"]
        )
        user_integrations.strava_token_expires_at = datetime.fromtimestamp(
            tokens["expires_at"]
        )

        # Set the strava state to None
        user_integrations.strava_state = None

        # Commit the changes to the database
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in link_strava_account: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def unlink_strava_account(user_id: int, db: Session):
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        # Check if user_integrations is None and return None if it is
        if user_integrations is None:
            # If the user was not found, return a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Set the user integrations Strava tokens to None
        user_integrations.strava_state = None
        user_integrations.strava_token = None
        user_integrations.strava_refresh_token = None
        user_integrations.strava_token_expires_at = None
        user_integrations.strava_sync_gear = False
        user_integrations.strava_client_id = None
        user_integrations.strava_client_secret = None

        # Commit the changes to the database
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in unlink_strava_account: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def set_user_strava_client(user_id: int, id: int, secret: str, db: Session):
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        # Check if user_integrations is None and return None if it is
        if user_integrations is None:
            # If the user was not found, return a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Set the user Strava client id and secret
        user_integrations.strava_client_id = core_cryptography.encrypt_token_fernet(id)
        user_integrations.strava_client_secret = core_cryptography.encrypt_token_fernet(
            secret
        )

        # Commit the changes to the database
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in set_user_strava_client: {err}",
            "error",
            exc=err,
            context={"id": "[REDACTED]", "secret": "[REDACTED]"},
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def set_user_strava_state(user_id: int, state: str | None, db: Session):
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        # Check if user_integrations is None and return None if it is
        if user_integrations is None:
            # If the user was not found, return a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Set the user Strava state
        user_integrations.strava_state = None if state in ("null", None) else state

        # Commit the changes to the database
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in set_user_strava_state: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def set_user_strava_sync_gear(user_id: int, strava_sync_gear: bool, db: Session):
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        # Set the user Strava state
        user_integrations.strava_sync_gear = strava_sync_gear

        # Commit the changes to the database
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in set_user_strava_sync_gear: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def link_garminconnect_account(
    user_id: int,
    oauth1_token: dict,
    oauth2_token: dict,
    db: Session,
):
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        # Check if user_integrations is None and return None if it is
        if user_integrations is None:
            # If the user was not found, return a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Update the user integrations with the tokens
        user_integrations.garminconnect_oauth1 = oauth1_token
        user_integrations.garminconnect_oauth2 = oauth2_token

        # Commit the changes to the database
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in link_garminconnect_account: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def set_user_garminconnect_sync_gear(
    user_id: int, garminconnect_sync_gear: bool, db: Session
):
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        # Set the user Garmin Connect state
        user_integrations.garminconnect_sync_gear = garminconnect_sync_gear

        # Commit the changes to the database
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in set_user_garminconnect_sync_gear: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def unlink_garminconnect_account(user_id: int, db: Session):
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        # Check if user_integrations is None and return None if it is
        if user_integrations is None:
            # If the user was not found, return a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Set the user integrations Garmin Connect tokens to None
        user_integrations.garminconnect_oauth1 = None
        user_integrations.garminconnect_oauth2 = None
        user_integrations.garminconnect_sync_gear = False

        # Commit the changes to the database
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in unlink_garminconnect_account: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_user_integrations(
    user_integrations: user_integrations_schema.UsersIntegrations,
    user_id: int,
    db: Session,
):
    try:
        # Get the user integrations from the database
        db_user_integrations = (
            db.query(user_integrations_models.UsersIntegrations)
            .filter(
                user_integrations_models.UsersIntegrations.user_id == user_id,
            )
            .first()
        )

        if db_user_integrations is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Dictionary of the fields to update if they are not None
        user_integrations_data = user_integrations.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_user dynamically
        for key, value in user_integrations_data.items():
            setattr(db_user_integrations, key, value)

        # Commit the transaction
        db.commit()

        return db_user_integrations
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in edit_user_integrations: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error: {err}",
        ) from err
