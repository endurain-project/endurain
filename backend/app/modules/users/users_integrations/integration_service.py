"""The operations other modules may call on a user's provider integrations.

Everything here returns schemas or primitives; no ORM row crosses the boundary. Writes
stage; the caller owns the commit.
"""

from sqlalchemy.orm import Session

import modules.users.users_integrations.crud as user_integrations_crud
import modules.users.users_integrations.schema as user_integrations_schema


def get_user_integrations(user_id: int, db: Session) -> user_integrations_schema.UsersIntegrationsRead | None:
    """Return a user's integrations, or ``None`` when the user has none.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The user's integrations, or ``None``.
    """
    return user_integrations_crud.get_user_integrations_by_user_id(user_id, db)


def replace_strava_tokens_if_refresh_token(user_id: int, old_refresh_token: str, tokens: dict, db: Session) -> bool:
    """Store refreshed Strava tokens only while the stored refresh token is still the one they came from.

    Args:
        user_id: The user whose tokens were refreshed.
        old_refresh_token: The stored (encrypted) refresh token the new tokens were refreshed from.
        tokens: Dictionary containing access_token, refresh_token, and expires_at.
        db: Database session.

    Returns:
        True when the tokens were replaced, False when the refresh token has since changed.
    """
    return user_integrations_crud.replace_strava_tokens_if_refresh_token(user_id, old_refresh_token, tokens, db)


def unlink_strava_tokens_if_refresh_token(user_id: int, refresh_token: str, db: Session) -> bool:
    """Clear a user's Strava tokens only while they still hold the given refresh token.

    Args:
        user_id: The user whose Strava link was rejected.
        refresh_token: The stored (encrypted) refresh token that was found to be rejected.
        db: Database session.

    Returns:
        True when the tokens were cleared, False when the refresh token has since changed.
    """
    return user_integrations_crud.unlink_strava_tokens_if_refresh_token(user_id, refresh_token, db)


def link_garminconnect_account(user_id: int, token: dict, db: Session) -> None:
    """Store a user's Garmin Connect token.

    Args:
        user_id: The user linking Garmin Connect.
        token: The serialized Garmin Connect token.
        db: Database session.
    """
    user_integrations_crud.link_garminconnect_account(user_id, token, db)


def unlink_garminconnect_account(user_id: int, db: Session) -> None:
    """Clear a user's Garmin Connect token and gear sync preference.

    Args:
        user_id: The user unlinking Garmin Connect.
        db: Database session.
    """
    user_integrations_crud.unlink_garminconnect_account(user_id, db)


def unlink_garminconnect_account_if_token(user_id: int, token: dict, db: Session) -> bool:
    """Clear a user's Garmin Connect token only while it is still the given one.

    Args:
        user_id: The user unlinking Garmin Connect.
        token: The stored token that was found to be rejected.
        db: Database session.

    Returns:
        True when the account was unlinked, False when the token has since changed.
    """
    return user_integrations_crud.unlink_garminconnect_account_if_token(user_id, token, db)


def replace_garminconnect_token_if_token(user_id: int, old_token: dict, new_token: dict, db: Session) -> bool:
    """Store a refreshed Garmin Connect token only while the stored one is still ``old_token``.

    Args:
        user_id: The user whose token to replace.
        old_token: The stored token the new one was refreshed from.
        new_token: The refreshed token.
        db: Database session.

    Returns:
        True when the token was replaced, False when the stored token has since changed.
    """
    return user_integrations_crud.replace_garminconnect_token_if_token(user_id, old_token, new_token, db)


def set_garminconnect_sync_gear(user_id: int, sync_gear: bool, db: Session) -> None:
    """Set whether a user's Garmin Connect gear is synchronised.

    Args:
        user_id: The user whose preference to set.
        sync_gear: Whether to synchronise gear.
        db: Database session.
    """
    user_integrations_crud.set_user_garminconnect_sync_gear(user_id, sync_gear, db)


def list_user_ids_with_garminconnect_linked(after_id: int, limit: int, db: Session) -> list[int]:
    """List the users who have linked Garmin Connect, ascending, a page at a time.

    Args:
        after_id: Return only users with an id greater than this.
        limit: Maximum number of user ids to return.
        db: Database session.

    Returns:
        The linked user ids, ascending.
    """
    return user_integrations_crud.list_user_ids_with_garminconnect_linked(after_id, limit, db)


def create_integrations(user_id: int, db: Session) -> user_integrations_schema.UsersIntegrationsRead:
    """Stage the default integrations row for a new user.

    Args:
        user_id: The user to create integrations for.
        db: Database session.

    Returns:
        The created integrations.

    Raises:
        ConflictError: If the user already has integrations.
    """
    return user_integrations_crud.create_user_integrations(user_id, db)


def edit_integrations(
    user_integrations: user_integrations_schema.UsersIntegrationsUpdate,
    user_id: int,
    db: Session,
) -> user_integrations_schema.UsersIntegrationsRead:
    """Stage an update of a user's integrations.

    Args:
        user_integrations: The fields to change.
        user_id: The user whose integrations to update.
        db: Database session.

    Returns:
        The updated integrations.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    return user_integrations_crud.edit_user_integrations(user_integrations, user_id, db)


def link_strava_account(user_id: int, tokens: dict, db: Session) -> None:
    """Store a user's Strava tokens (encrypted).

    Args:
        user_id: The user linking Strava.
        tokens: The token response holding ``access_token``, ``refresh_token`` and ``expires_at``.
        db: Database session.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    user_integrations_crud.link_strava_account(user_id, tokens, db)


def unlink_strava_account(user_id: int, db: Session) -> None:
    """Clear a user's Strava tokens, credentials and gear sync preference.

    Args:
        user_id: The user unlinking Strava.
        db: Database session.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    user_integrations_crud.unlink_strava_account(user_id, db)


def set_strava_client(user_id: int, client_id: str, client_secret: str, db: Session, *, if_match: str) -> None:
    """Store a user's Strava client credentials (encrypted).

    Args:
        user_id: The user whose credentials to set.
        client_id: The Strava client id.
        client_secret: The Strava client secret.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no integrations.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    user_integrations_crud.set_user_strava_client(user_id, client_id, client_secret, db, if_match=if_match)


def set_strava_sync_gear(user_id: int, sync_gear: bool, db: Session) -> None:
    """Set whether a user's Strava gear is synchronised.

    Args:
        user_id: The user whose preference to set.
        sync_gear: Whether to synchronise gear.
        db: Database session.

    Raises:
        NotFoundError: If the user has no integrations.
    """
    user_integrations_crud.set_user_strava_sync_gear(user_id, sync_gear, db)


def list_user_ids_with_strava_linked(after_id: int, limit: int, db: Session) -> list[int]:
    """List the users who have linked Strava, ascending, a page at a time.

    Args:
        after_id: Return only users with an id greater than this.
        limit: Maximum number of user ids to return.
        db: Database session.

    Returns:
        The linked user ids, ascending.
    """
    return user_integrations_crud.list_user_ids_with_strava_linked(after_id, limit, db)
