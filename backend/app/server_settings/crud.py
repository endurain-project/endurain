from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import server_settings.schema as server_settings_schema
import server_settings.models as server_settings_models
import server_settings.utils as server_settings_utils

import core.cryptography as core_cryptography
import core.decorators as core_decorators


@core_decorators.handle_db_errors
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
    # Get the server settings from the database
    stmt = select(server_settings_models.ServerSettings).where(
        server_settings_models.ServerSettings.id == 1
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
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
    # Get the server_settings from the database
    db_server_settings = server_settings_utils.get_server_settings_or_404(db)

    if server_settings.tileserver_api_key is not None:
        # Encrypt the tile server API key before storing
        encrypted_api_key = core_cryptography.encrypt_token_fernet(
            server_settings.tileserver_api_key
        )
        server_settings.tileserver_api_key = encrypted_api_key

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


@core_decorators.handle_db_errors
def update_server_settings_login_photo_set(is_set: bool, db: Session) -> None:
    # Get the server_settings from the database
    db_server_settings = server_settings_utils.get_server_settings_or_404(db)

    db_server_settings.login_photo_set = is_set

    # Commit the transaction
    db.commit()
    # Refresh the object to ensure it reflects database state
    db.refresh(db_server_settings)
