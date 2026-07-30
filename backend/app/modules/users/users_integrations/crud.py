"""CRUD operations for user integrations."""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.decorators as core_decorators
import modules.users.users_integrations.models as user_integrations_models
import modules.users.users_integrations.schema as user_integrations_schema

# Private internal helpers


def _transform_users_integrations(
    users: user_integrations_models.UsersIntegrations,
) -> user_integrations_schema.UsersIntegrationsRead:
    """
    Transform a user integrations instance to a Pydantic schema.

    Args:
        users: The user integrations ORM instance.

    Returns:
        The user integrations as a schema.
    """
    return user_integrations_schema.UsersIntegrationsRead.model_validate(users)


@core_decorators.handle_db_errors
def _get_user_integrations_model_by_user_id_or_404(
    user_id: int, db: Session
) -> user_integrations_models.UsersIntegrations:
    """
    Retrieve integrations for a specific user.

    Args:
        user_id: The ID of the user to fetch integrations for.
        db: SQLAlchemy database session.

    Returns:
        The UsersIntegrations ORM model for the user.

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database query fails.
    """
    # Get the user integrations by the user id
    stmt = select(user_integrations_models.UsersIntegrations).where(
        user_integrations_models.UsersIntegrations.user_id == user_id
    )
    db_user_integrations = db.execute(stmt).scalar_one_or_none()

    if not db_user_integrations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User integrations not found",
        )

    return db_user_integrations


# Public CRUD functions


@core_decorators.handle_db_errors
def get_user_integrations_by_user_id(
    user_id: int, db: Session
) -> user_integrations_schema.UsersIntegrationsRead | None:
    """
    Retrieve integrations for a specific user.

    Args:
        user_id: The ID of the user to fetch integrations for.
        db: SQLAlchemy database session.

    Returns:
        The UsersIntegrationsRead schema for the user.

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database query fails.
    """
    # Get the user integrations by the user id
    stmt = select(user_integrations_models.UsersIntegrations).where(
        user_integrations_models.UsersIntegrations.user_id == user_id
    )
    user_integrations = db.execute(stmt).scalar_one_or_none()
    return _transform_users_integrations(user_integrations) if user_integrations else None


@core_decorators.handle_db_errors
def get_user_integrations_by_strava_state(
    strava_state: str, db: Session
) -> user_integrations_schema.UsersIntegrationsRead | None:
    """
    Retrieve integrations by Strava OAuth state token.

    Args:
        strava_state: The Strava OAuth state to search for.
        db: SQLAlchemy database session.

    Returns:
        The UsersIntegrationsRead schema if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    # Get user integrations based on the strava state
    stmt = select(user_integrations_models.UsersIntegrations).where(
        user_integrations_models.UsersIntegrations.strava_state == strava_state
    )
    user_integrations = db.execute(stmt).scalar_one_or_none()
    return _transform_users_integrations(user_integrations) if user_integrations else None


@core_decorators.handle_db_errors
def create_user_integrations(user_id: int, db: Session) -> user_integrations_schema.UsersIntegrationsRead:
    """
    Create integration settings for a user.

    Args:
        user_id: The ID of the user to create integrations for.
        db: SQLAlchemy database session.

    Returns:
        The created UsersIntegrationsRead schema.

    Raises:
        HTTPException: 409 error if integrations already exist.
        HTTPException: 500 error if database operation fails.
    """
    try:
        # Create a new user integrations with model defaults
        user_integrations = user_integrations_models.UsersIntegrations(
            user_id=user_id,
        )

        # Add the user integrations to the database
        db.add(user_integrations)
        db.commit()
        db.refresh(user_integrations)

        # Return the user integrations
        return _transform_users_integrations(user_integrations)
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Integrations already exist for this user",
        ) from integrity_error


@core_decorators.handle_db_errors
def link_strava_account(
    user_id: int,
    tokens: dict,
    db: Session,
) -> None:
    """
    Link a Strava account by storing OAuth tokens.

    Args:
        user_id: The ID of the user to update.
        tokens: Dictionary containing access_token,
            refresh_token, and expires_at.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Update the user integrations with the tokens
    db_user_integrations.strava_token = core_cryptography.encrypt_token_fernet(tokens["access_token"])
    db_user_integrations.strava_refresh_token = core_cryptography.encrypt_token_fernet(tokens["refresh_token"])
    db_user_integrations.strava_token_expires_at = datetime.fromtimestamp(tokens["expires_at"], tz=UTC)

    # Set the strava state to None
    db_user_integrations.strava_state = None

    # Commit the changes to the database
    db.commit()
    db.refresh(db_user_integrations)


@core_decorators.handle_db_errors
def unlink_strava_account(user_id: int, db: Session) -> None:
    """
    Unlink a Strava account by clearing OAuth tokens.

    Args:
        user_id: The ID of the user to unlink.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database operation fails.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Clear all Strava integration data
    db_user_integrations.strava_state = None
    db_user_integrations.strava_token = None
    db_user_integrations.strava_refresh_token = None
    db_user_integrations.strava_token_expires_at = None
    db_user_integrations.strava_sync_gear = False
    db_user_integrations.strava_client_id = None
    db_user_integrations.strava_client_secret = None

    # Commit the changes to the database
    db.commit()
    db.refresh(db_user_integrations)


@core_decorators.handle_db_errors
def set_user_strava_client(user_id: int, client_id: str, client_secret: str, db: Session) -> None:
    """
    Set Strava client credentials for a user.

    Args:
        user_id: The ID of the user.
        client_id: Strava client ID to encrypt and store.
        client_secret: Strava client secret to encrypt and store.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database operation fails.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Encrypt and store Strava client credentials
    db_user_integrations.strava_client_id = core_cryptography.encrypt_token_fernet(client_id)
    db_user_integrations.strava_client_secret = core_cryptography.encrypt_token_fernet(client_secret)

    # Commit the changes to the database
    db.commit()
    db.refresh(db_user_integrations)


@core_decorators.handle_db_errors
def set_user_strava_state(user_id: int, state: str | None, db: Session) -> None:
    """
    Set or clear Strava OAuth state for a user.

    Args:
        user_id: The ID of the user.
        state: Strava OAuth state to set, or None to clear.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database operation fails.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Set the user Strava state
    db_user_integrations.strava_state = None if state in ("null", None) else state

    # Commit the changes to the database
    db.commit()
    db.refresh(db_user_integrations)


@core_decorators.handle_db_errors
def set_user_strava_sync_gear(user_id: int, strava_sync_gear: bool, db: Session) -> None:
    """
    Set Strava gear synchronization preference for a user.

    Args:
        user_id: The ID of the user.
        strava_sync_gear: Whether to sync gear from Strava.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database operation fails.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Set the Strava gear sync preference
    db_user_integrations.strava_sync_gear = strava_sync_gear

    # Commit the changes to the database
    db.commit()
    db.refresh(db_user_integrations)


@core_decorators.handle_db_errors
def link_garminconnect_account(
    user_id: int,
    token: dict,
    db: Session,
) -> None:
    """
    Link a Garmin Connect account by storing token.

    Args:
        user_id: The ID of the user.
        token: Garmin Connect token data.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database operation fails.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Store Garmin Connect token
    db_user_integrations.garminconnect_token = token

    # Commit the changes to the database
    db.commit()
    db.refresh(db_user_integrations)


@core_decorators.handle_db_errors
def set_user_garminconnect_sync_gear(user_id: int, garminconnect_sync_gear: bool, db: Session) -> None:
    """
    Set Garmin Connect gear synchronization preference.

    Args:
        user_id: The ID of the user.
        garminconnect_sync_gear: Whether to sync gear from
            Garmin Connect.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database operation fails.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Set the Garmin Connect gear sync preference
    db_user_integrations.garminconnect_sync_gear = garminconnect_sync_gear

    # Commit the changes to the database
    db.commit()
    db.refresh(db_user_integrations)


@core_decorators.handle_db_errors
def unlink_garminconnect_account(user_id: int, db: Session) -> None:
    """
    Unlink a Garmin Connect account by clearing OAuth tokens.

    Args:
        user_id: The ID of the user to unlink.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database operation fails.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Clear all Garmin Connect integration data
    db_user_integrations.garminconnect_token = None
    db_user_integrations.garminconnect_sync_gear = False

    # Commit the changes to the database
    db.commit()
    db.refresh(db_user_integrations)


@core_decorators.handle_db_errors
def edit_user_integrations(
    user_integrations: user_integrations_schema.UsersIntegrationsUpdate,
    user_id: int,
    db: Session,
) -> user_integrations_schema.UsersIntegrationsRead:
    """
    Update user integration settings.

    Args:
        user_integrations: Schema with fields to update.
        user_id: The ID of the user to update.
        db: SQLAlchemy database session.

    Returns:
        The updated UsersIntegrations model.

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database operation fails.
    """
    # Get the user integrations from the database
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Get fields to update
    user_integrations_data = user_integrations.model_dump(exclude_unset=True, exclude={"user_id", "id"})
    # Update fields dynamically
    for key, value in user_integrations_data.items():
        setattr(db_user_integrations, key, value)

    # Commit the transaction
    db.commit()
    db.refresh(db_user_integrations)
    return _transform_users_integrations(db_user_integrations)
