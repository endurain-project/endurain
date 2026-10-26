"""CRUD operations for user integrations."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.users.users_integrations.models as user_integrations_models
import modules.users.users_integrations.schema as user_integrations_schema
import modules.users.users_integrations.serializers as user_integrations_serializers


def _get_user_integrations_model_by_user_id_or_404(
    user_id: int, db: Session
) -> user_integrations_models.UsersIntegrations:
    """Retrieve integrations for a specific user.

    Args:
        user_id: The ID of the user to fetch integrations for.
        db: SQLAlchemy database session.

    Returns:
        The UsersIntegrations ORM model for the user.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    # Get the user integrations by the user id
    stmt = select(user_integrations_models.UsersIntegrations).where(
        user_integrations_models.UsersIntegrations.user_id == user_id
    )
    db_user_integrations = db.execute(stmt).scalar_one_or_none()

    if not db_user_integrations:
        raise core_exceptions.NotFoundError("User integrations not found")

    return db_user_integrations


def get_user_integrations_by_user_id(
    user_id: int, db: Session
) -> user_integrations_schema.UsersIntegrationsRead | None:
    """Retrieve integrations for a specific user.

    Args:
        user_id: The ID of the user to fetch integrations for.
        db: SQLAlchemy database session.

    Returns:
        The UsersIntegrationsRead schema for the user, or None if the user has none.
    """
    # Get the user integrations by the user id
    stmt = select(user_integrations_models.UsersIntegrations).where(
        user_integrations_models.UsersIntegrations.user_id == user_id
    )
    user_integrations = db.execute(stmt).scalar_one_or_none()
    return user_integrations_serializers.to_read_schema(user_integrations) if user_integrations else None


def list_user_ids_with_strava_linked(after_id: int, limit: int, db: Session) -> list[int]:
    """List the users who have linked Strava, ascending, a page at a time.

    Args:
        after_id: Return only users with an id greater than this.
        limit: Maximum number of user ids to return.
        db: SQLAlchemy database session.

    Returns:
        User ids with a stored Strava token, ascending.
    """
    stmt = (
        select(user_integrations_models.UsersIntegrations.user_id)
        .where(
            user_integrations_models.UsersIntegrations.user_id > after_id,
            user_integrations_models.UsersIntegrations.strava_token.is_not(None),
        )
        .order_by(user_integrations_models.UsersIntegrations.user_id)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def list_user_ids_with_garminconnect_linked(after_id: int, limit: int, db: Session) -> list[int]:
    """List the users who have linked Garmin Connect, ascending, a page at a time.

    The token is a JSON column, and unlinking assigns ``None``, which is stored as
    a JSON ``null`` rather than SQL ``NULL``. A SQL ``IS NOT NULL`` would therefore
    still match unlinked users, so rows are scanned in id order and filtered on the
    decoded value until a page is full.

    Args:
        after_id: Return only users with an id greater than this.
        limit: Maximum number of user ids to return.
        db: SQLAlchemy database session.

    Returns:
        User ids with a stored Garmin Connect token, ascending.
    """
    linked: list[int] = []
    cursor = after_id
    while len(linked) < limit:
        stmt = (
            select(
                user_integrations_models.UsersIntegrations.user_id,
                user_integrations_models.UsersIntegrations.garminconnect_token,
            )
            .where(user_integrations_models.UsersIntegrations.user_id > cursor)
            .order_by(user_integrations_models.UsersIntegrations.user_id)
            .limit(limit)
        )
        rows = db.execute(stmt).all()
        if not rows:
            break
        cursor = rows[-1][0]
        linked.extend(user_id for user_id, token in rows if token is not None)
    return linked[:limit]


def create_user_integrations(user_id: int, db: Session) -> user_integrations_schema.UsersIntegrationsRead:
    """Create integration settings for a user (flushed, not committed).

    Args:
        user_id: The ID of the user to create integrations for.
        db: SQLAlchemy database session.

    Returns:
        The created UsersIntegrationsRead schema.

    Raises:
        ConflictError: If integrations already exist.
    """
    try:
        # Create a new user integrations with model defaults
        user_integrations = user_integrations_models.UsersIntegrations(
            user_id=user_id,
        )

        # Add the user integrations to the database
        db.add(user_integrations)
        db.flush()
        db.refresh(user_integrations)

        # Return the user integrations
        return user_integrations_serializers.to_read_schema(user_integrations)
    except IntegrityError as err:
        raise core_exceptions.ConflictError("Integrations already exist for this user") from err


def link_strava_account(
    user_id: int,
    tokens: dict,
    db: Session,
) -> None:
    """Link a Strava account by storing OAuth tokens (flushed, not committed).

    Args:
        user_id: The ID of the user to update.
        tokens: Dictionary containing access_token,
            refresh_token, and expires_at.
        db: SQLAlchemy database session.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Update the user integrations with the tokens
    db_user_integrations.strava_token = core_cryptography.encrypt_token_fernet(tokens["access_token"])
    db_user_integrations.strava_refresh_token = core_cryptography.encrypt_token_fernet(tokens["refresh_token"])
    db_user_integrations.strava_token_expires_at = datetime.fromtimestamp(tokens["expires_at"], tz=UTC)

    db.flush()
    db.refresh(db_user_integrations)


def replace_strava_tokens_if_refresh_token(user_id: int, old_refresh_token: str, tokens: dict, db: Session) -> bool:
    """Store refreshed Strava tokens only while the stored refresh token is still the one they came from.

    Strava rotates the refresh token on every refresh. The row is locked while the token is
    compared, so a refresh that raced another, or a relink made in the meantime, is never
    overwritten. The caller commits.

    Args:
        user_id: The ID of the user.
        old_refresh_token: The stored (encrypted) refresh token the new tokens were refreshed from.
        tokens: Dictionary containing access_token, refresh_token, and expires_at.
        db: SQLAlchemy database session.

    Returns:
        True when the tokens were replaced, False when the stored refresh token has changed or is cleared.
    """
    stmt = (
        select(user_integrations_models.UsersIntegrations)
        .where(user_integrations_models.UsersIntegrations.user_id == user_id)
        .with_for_update()
    )
    db_user_integrations = db.execute(stmt).scalar_one_or_none()

    if db_user_integrations is None or db_user_integrations.strava_refresh_token != old_refresh_token:
        return False

    db_user_integrations.strava_token = core_cryptography.encrypt_token_fernet(tokens["access_token"])
    db_user_integrations.strava_refresh_token = core_cryptography.encrypt_token_fernet(tokens["refresh_token"])
    db_user_integrations.strava_token_expires_at = datetime.fromtimestamp(tokens["expires_at"], tz=UTC)
    return True


def unlink_strava_account(user_id: int, db: Session) -> None:
    """Unlink a Strava account by clearing OAuth tokens (flushed, not committed).

    Args:
        user_id: The ID of the user to unlink.
        db: SQLAlchemy database session.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Clear all Strava integration data
    db_user_integrations.strava_token = None
    db_user_integrations.strava_refresh_token = None
    db_user_integrations.strava_token_expires_at = None
    db_user_integrations.strava_sync_gear = False
    db_user_integrations.strava_client_id = None
    db_user_integrations.strava_client_secret = None

    db.flush()
    db.refresh(db_user_integrations)


def unlink_strava_tokens_if_refresh_token(user_id: int, refresh_token: str, db: Session) -> bool:
    """Clear a user's Strava tokens only while they still hold the given refresh token.

    The client id and secret are kept, so the user relinks without entering them again. The
    row is locked while the token is compared, so a link or refresh made in the meantime is
    never cleared by a caller that holds the previous token. The caller commits.

    Args:
        user_id: The ID of the user to unlink.
        refresh_token: The stored (encrypted) refresh token the caller found to be rejected.
        db: SQLAlchemy database session.

    Returns:
        True when the tokens were cleared, False when the stored refresh token has changed or
        is already cleared.
    """
    stmt = (
        select(user_integrations_models.UsersIntegrations)
        .where(user_integrations_models.UsersIntegrations.user_id == user_id)
        .with_for_update()
    )
    db_user_integrations = db.execute(stmt).scalar_one_or_none()

    if db_user_integrations is None or db_user_integrations.strava_refresh_token != refresh_token:
        return False

    db_user_integrations.strava_token = None
    db_user_integrations.strava_refresh_token = None
    db_user_integrations.strava_token_expires_at = None
    db_user_integrations.strava_sync_gear = False
    return True


def set_user_strava_client(user_id: int, client_id: str, client_secret: str, db: Session) -> None:
    """Set Strava client credentials for a user (flushed, not committed).

    Args:
        user_id: The ID of the user.
        client_id: Strava client ID to encrypt and store.
        client_secret: Strava client secret to encrypt and store.
        db: SQLAlchemy database session.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Encrypt and store Strava client credentials
    db_user_integrations.strava_client_id = core_cryptography.encrypt_token_fernet(client_id)
    db_user_integrations.strava_client_secret = core_cryptography.encrypt_token_fernet(client_secret)

    db.flush()
    db.refresh(db_user_integrations)


def set_user_strava_sync_gear(user_id: int, strava_sync_gear: bool, db: Session) -> None:
    """Set Strava gear synchronization preference for a user (flushed, not committed).

    Args:
        user_id: The ID of the user.
        strava_sync_gear: Whether to sync gear from Strava.
        db: SQLAlchemy database session.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Set the Strava gear sync preference
    db_user_integrations.strava_sync_gear = strava_sync_gear

    db.flush()
    db.refresh(db_user_integrations)


def link_garminconnect_account(
    user_id: int,
    token: dict,
    db: Session,
) -> None:
    """Link a Garmin Connect account by storing token.

    The caller commits.

    Args:
        user_id: The ID of the user.
        token: Garmin Connect token data.
        db: SQLAlchemy database session.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Store Garmin Connect token
    db_user_integrations.garminconnect_token = token


def set_user_garminconnect_sync_gear(user_id: int, garminconnect_sync_gear: bool, db: Session) -> None:
    """Set Garmin Connect gear synchronization preference (flushed, not committed).

    Args:
        user_id: The ID of the user.
        garminconnect_sync_gear: Whether to sync gear from
            Garmin Connect.
        db: SQLAlchemy database session.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Set the Garmin Connect gear sync preference
    db_user_integrations.garminconnect_sync_gear = garminconnect_sync_gear

    db.flush()
    db.refresh(db_user_integrations)


def unlink_garminconnect_account(user_id: int, db: Session) -> None:
    """Unlink a Garmin Connect account by clearing OAuth tokens.

    The caller commits.

    Args:
        user_id: The ID of the user to unlink.
        db: SQLAlchemy database session.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    # Get the user integrations by the user id
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Clear all Garmin Connect integration data
    db_user_integrations.garminconnect_token = None
    db_user_integrations.garminconnect_sync_gear = False


def unlink_garminconnect_account_if_token(user_id: int, token: dict, db: Session) -> bool:
    """Unlink a Garmin Connect account only while it still holds the given token.

    The row is locked while the token is compared, so a link made in the meantime is
    never cleared by a caller that holds the previous token. The caller commits.

    Args:
        user_id: The ID of the user to unlink.
        token: The stored token the caller found to be rejected.
        db: SQLAlchemy database session.

    Returns:
        True when the account was unlinked, False when the stored token has changed or
        is already cleared.
    """
    stmt = (
        select(user_integrations_models.UsersIntegrations)
        .where(user_integrations_models.UsersIntegrations.user_id == user_id)
        .with_for_update()
    )
    db_user_integrations = db.execute(stmt).scalar_one_or_none()

    if db_user_integrations is None or db_user_integrations.garminconnect_token != token:
        return False

    db_user_integrations.garminconnect_token = None
    db_user_integrations.garminconnect_sync_gear = False
    return True


def replace_garminconnect_token_if_token(user_id: int, old_token: dict, new_token: dict, db: Session) -> bool:
    """Replace a Garmin Connect token only while it is still the given one.

    The row is locked while the token is compared, so a token refreshed by a finished sync never
    overwrites one linked in the meantime. The caller commits.

    Args:
        user_id: The ID of the user.
        old_token: The stored token the new one was refreshed from.
        new_token: The refreshed token to store.
        db: SQLAlchemy database session.

    Returns:
        True when the token was replaced, False when the stored token has changed or is cleared.
    """
    stmt = (
        select(user_integrations_models.UsersIntegrations)
        .where(user_integrations_models.UsersIntegrations.user_id == user_id)
        .with_for_update()
    )
    db_user_integrations = db.execute(stmt).scalar_one_or_none()

    if db_user_integrations is None or db_user_integrations.garminconnect_token != old_token:
        return False

    db_user_integrations.garminconnect_token = new_token
    return True


def edit_user_integrations(
    user_integrations: user_integrations_schema.UsersIntegrationsUpdate,
    user_id: int,
    db: Session,
) -> user_integrations_schema.UsersIntegrationsRead:
    """Update user integration settings (flushed, not committed).

    Args:
        user_integrations: Schema with fields to update.
        user_id: The ID of the user to update.
        db: SQLAlchemy database session.

    Returns:
        The updated UsersIntegrations model.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    # Get the user integrations from the database
    db_user_integrations = _get_user_integrations_model_by_user_id_or_404(user_id, db)

    # Get fields to update
    user_integrations_data = user_integrations.model_dump(exclude_unset=True, exclude={"user_id", "id"})
    # Update fields dynamically
    for key, value in user_integrations_data.items():
        setattr(db_user_integrations, key, value)

    db.flush()
    db.refresh(db_user_integrations)
    return user_integrations_serializers.to_read_schema(db_user_integrations)
