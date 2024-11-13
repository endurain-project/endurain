import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

import user_integrations.schema as user_integrations_schema
import models

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def get_user_integrations_by_user_id(user_id: int, db: Session):
    try:
        # Get the user integrations by the user id
        user_integrations = (
            db.query(models.UserIntegrations)
            .filter(models.UserIntegrations.user_id == user_id)
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
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_user_integrations_by_user_id: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_integrations_by_strava_state(strava_state: str, db: Session):
    try:
        user_integrations = (
            db.query(models.UserIntegrations)
            .filter(models.UserIntegrations.strava_state == strava_state)
            .first()
        )

        # Check if user_integrations is None and return None if it is
        if user_integrations is None:
            return None

        # Return the user integrations
        return user_integrations
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_user_integrations_by_user_id: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_user_integrations(user_id: int, db: Session):
    try:
        # Create a new user integrations
        user_integrations = models.UserIntegrations(
            user_id=user_id,
            strava_sync_gear=False,
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
        logger.error(f"Error in create_user_integrations: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def link_strava_account(
    user_integrations: user_integrations_schema.UserIntegrations,
    tokens: dict,
    db: Session,
):
    try:
        # Update the user integrations with the tokens
        user_integrations.strava_token = tokens["access_token"]
        user_integrations.strava_refresh_token = tokens["refresh_token"]
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
        logger.error(f"Error in link_strava_account: {err}", exc_info=True)

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
        user_integrations.strava_token = None
        user_integrations.strava_refresh_token = None
        user_integrations.strava_token_expires_at = None
        user_integrations.strava_sync_gear = False

        # Commit the changes to the database
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(f"Error in link_strava_account: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def set_user_strava_state(user_id: int, state: str, db: Session):
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
        user_integrations.strava_state = state

        # Commit the changes to the database
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(f"Error in set_user_strava_state: {err}", exc_info=True)

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
        logger.error(f"Error in set_user_strava_state: {err}", exc_info=True)

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
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(f"Error in link_garminconnect_account: {err}", exc_info=True)

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

        # Commit the changes to the database
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(f"Error in unlink_garminconnect_account: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err