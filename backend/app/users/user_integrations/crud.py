"""CRUD operations for user integrations."""

from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import users.user_integrations.schema as user_integrations_schema
import users.user_integrations.models as user_integrations_models

import core.cryptography as core_cryptography
import core.logger as core_logger


def get_user_integrations_by_user_id(
    user_id: int, db: Session
) -> user_integrations_models.UsersIntegrations | None:
    """
    Retrieve integrations for a specific user.

    Args:
        user_id: The ID of the user to fetch integrations for.
        db: SQLAlchemy database session.

    Returns:
        The UsersIntegrations model for the user.

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database query fails.
    """
    try:
        # Get the user integrations by the user id
        stmt = select(user_integrations_models.UsersIntegrations).where(
            user_integrations_models.UsersIntegrations.user_id == user_id
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_user_integrations_by_user_id: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_user_integrations_by_strava_state(
    strava_state: str, db: Session
) -> user_integrations_models.UsersIntegrations | None:
    """
    Retrieve integrations by Strava OAuth state token.

    Args:
        strava_state: The Strava OAuth state to search for.
        db: SQLAlchemy database session.

    Returns:
        The UsersIntegrations model if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    try:
        # Get user integrations based on the strava state
        stmt = select(user_integrations_models.UsersIntegrations).where(
            user_integrations_models.UsersIntegrations.strava_state == strava_state
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        # Log the exception
        core_logger.print_to_log(
            f"Database error in get_user_integrations_by_strava_state: {db_err}",
            "error",
            exc=db_err,
        )
        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def create_user_integrations(
    user_id: int, db: Session
) -> user_integrations_models.UsersIntegrations:
    """
    Create integration settings for a user.

    Args:
        user_id: The ID of the user to create integrations for.
        db: SQLAlchemy database session.

    Returns:
        The created UsersIntegrations model.

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
        return user_integrations
    except IntegrityError as integrity_error:
        # Rollback the transaction
        db.rollback()

        # Raise an HTTPException with a 409 Conflict status code
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Integrations already exist for this user",
        ) from integrity_error
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in create_user_integrations: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def link_strava_account(
    user_integrations: user_integrations_models.UsersIntegrations,
    tokens: dict,
    db: Session,
) -> None:
    """
    Link a Strava account by storing OAuth tokens.

    Args:
        user_integrations: The UsersIntegrations ORM model to
            update.
        tokens: Dictionary containing access_token,
            refresh_token, and expires_at.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 500 error if database operation fails.
    """
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
        db.refresh(user_integrations)
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in link_strava_account: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


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
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        if user_integrations is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Clear all Strava integration data
        user_integrations.strava_state = None
        user_integrations.strava_token = None
        user_integrations.strava_refresh_token = None
        user_integrations.strava_token_expires_at = None
        user_integrations.strava_sync_gear = False
        user_integrations.strava_client_id = None
        user_integrations.strava_client_secret = None

        # Commit the changes to the database
        db.commit()
        db.refresh(user_integrations)
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in unlink_strava_account: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def set_user_strava_client(
    user_id: int, client_id: str, client_secret: str, db: Session
) -> None:
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
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        if user_integrations is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Encrypt and store Strava client credentials
        user_integrations.strava_client_id = core_cryptography.encrypt_token_fernet(
            client_id
        )
        user_integrations.strava_client_secret = core_cryptography.encrypt_token_fernet(
            client_secret
        )

        # Commit the changes to the database
        db.commit()
        db.refresh(user_integrations)
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in set_user_strava_client: {db_err}",
            "error",
            exc=db_err,
            context={"id": "[REDACTED]", "secret": "[REDACTED]"},
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


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
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        if user_integrations is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Set the user Strava state
        user_integrations.strava_state = None if state in ("null", None) else state

        # Commit the changes to the database
        db.commit()
        db.refresh(user_integrations)
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in set_user_strava_state: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def set_user_strava_sync_gear(
    user_id: int, strava_sync_gear: bool, db: Session
) -> None:
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
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        if user_integrations is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Set the Strava gear sync preference
        user_integrations.strava_sync_gear = strava_sync_gear

        # Commit the changes to the database
        db.commit()
        db.refresh(user_integrations)
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in set_user_strava_sync_gear: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def link_garminconnect_account(
    user_id: int,
    oauth1_token: dict,
    oauth2_token: dict,
    db: Session,
) -> None:
    """
    Link a Garmin Connect account by storing OAuth tokens.

    Args:
        user_id: The ID of the user.
        oauth1_token: Garmin Connect OAuth1 token data.
        oauth2_token: Garmin Connect OAuth2 token data.
        db: SQLAlchemy database session.

    Returns:
        None

    Raises:
        HTTPException: 404 error if integrations not found.
        HTTPException: 500 error if database operation fails.
    """
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        if user_integrations is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Store Garmin Connect OAuth tokens
        user_integrations.garminconnect_oauth1 = oauth1_token
        user_integrations.garminconnect_oauth2 = oauth2_token

        # Commit the changes to the database
        db.commit()
        db.refresh(user_integrations)
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in link_garminconnect_account: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def set_user_garminconnect_sync_gear(
    user_id: int, garminconnect_sync_gear: bool, db: Session
) -> None:
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
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        if user_integrations is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Set the Garmin Connect gear sync preference
        user_integrations.garminconnect_sync_gear = garminconnect_sync_gear

        # Commit the changes to the database
        db.commit()
        db.refresh(user_integrations)
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in set_user_garminconnect_sync_gear: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


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
    try:
        # Get the user integrations by the user id
        user_integrations = get_user_integrations_by_user_id(user_id, db)

        if user_integrations is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Clear all Garmin Connect integration data
        user_integrations.garminconnect_oauth1 = None
        user_integrations.garminconnect_oauth2 = None
        user_integrations.garminconnect_sync_gear = False

        # Commit the changes to the database
        db.commit()
        db.refresh(user_integrations)
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in unlink_garminconnect_account: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def edit_user_integrations(
    user_integrations: user_integrations_schema.UsersIntegrationsUpdate,
    user_id: int,
    db: Session,
) -> user_integrations_models.UsersIntegrations:
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
    try:
        # Get the user integrations from the database
        db_user_integrations = get_user_integrations_by_user_id(user_id, db)

        if db_user_integrations is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Get fields to update
        user_integrations_data = user_integrations.model_dump(exclude_unset=True)
        # Update fields dynamically
        for key, value in user_integrations_data.items():
            setattr(db_user_integrations, key, value)

        # Commit the transaction
        db.commit()
        db.refresh(db_user_integrations)
        return db_user_integrations
    except HTTPException as http_err:
        raise http_err
    except SQLAlchemyError as db_err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Database error in edit_user_integrations: {db_err}",
            "error",
            exc=db_err,
        )

        # Raise an HTTPException with a 500 status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err
