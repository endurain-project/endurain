from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from urllib.parse import unquote

import session.security as session_security

import server_settings.schema as server_settings_schema
import server_settings.models as server_settings_models

import core.logger as core_logger


def get_server_settings(db: Session):
    try:
        # Get the user from the database
        server_settings = (
            db.query(server_settings_models.ServerSettings)
            .filter(server_settings_models.ServerSettings.id == 1)
            .first()
        )

        # If the server_settings was not found, return None
        if server_settings is None:
            return None

        # Return the server_settings
        return server_settings
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_server_settings: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error: {err}",
        ) from err
    

def edit_server_settings(server_settings: server_settings_schema.ServerSettings, db: Session):
    try:
        # Get the server_settings from the database
        db_server_settings = (
            db.query(server_settings_models.ServerSettings).filter(server_settings_models.ServerSettings.id == 1).first()
        )

        if db_server_settings is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server settings not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Dictionary of the fields to update if they are not None
        server_settings_data = server_settings.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_user dynamically
        for key, value in server_settings_data.items():
            setattr(db_server_settings, key, value)

        # Commit the transaction
        db.commit()

        return db_server_settings
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in edit_server_settings: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error: {err}",
        ) from err
