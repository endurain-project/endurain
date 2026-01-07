from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

import server_settings.schema as server_settings_schema
import server_settings.models as server_settings_models

import core.logger as core_logger


def get_server_settings(db: Session) -> server_settings_models.ServerSettings | None:
    """
    Retrieve singleton server settings from database.

    Args:
        db: Database session.

    Returns:
        ServerSettings instance or None if not found.

    Raises:
        HTTPException: If database error occurs.
    """
    try:
        # Get the server settings from the database
        stmt = select(server_settings_models.ServerSettings).where(
            server_settings_models.ServerSettings.id == 1
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_server_settings: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def edit_server_settings(
    server_settings: server_settings_schema.ServerSettingsEdit, db: Session
) -> server_settings_models.ServerSettings:
    """
    Update server settings in database.

    Args:
        server_settings: New settings to apply.
        db: Database session.

    Returns:
        Updated ServerSettings instance.

    Raises:
        HTTPException: If settings not found or database error.
    """
    try:
        # Get the server_settings from the database
        db_server_settings = get_server_settings(db)

        if db_server_settings is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server settings not found",
            ) from None

        # Dictionary of the fields to update if they are not None
        server_settings_data = server_settings.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_user dynamically
        for key, value in server_settings_data.items():
            setattr(db_server_settings, key, value)

        # Commit the transaction
        db.commit()
        # Refresh the object to ensure it reflects database state
        db.refresh(db_server_settings)

        return db_server_settings
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in edit_server_settings: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err
