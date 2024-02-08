import logging

import models

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def get_user_integrations_by_user_id(user_id: int, db: Session):
    try:
        user_integrations = (
            db.query(models.UserIntegrations)
            .filter(models.UserIntegrations.user_id == user_id)
            .first()
        )
        if user_integrations is None:
            # If the user was not found, return a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )
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
            user_id = user_id,
            strava_sync_gear = False,
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