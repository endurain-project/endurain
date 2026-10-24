"""The operations other modules may call on a user's provider integrations.

Everything here returns schemas or primitives; no ORM row crosses the boundary.
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


def link_garminconnect_account(user_id: int, token: dict, db: Session) -> None:
    """Store a user's Garmin Connect token; the caller commits.

    Args:
        user_id: The user linking Garmin Connect.
        token: The serialized Garmin Connect token.
        db: Database session.
    """
    user_integrations_crud.link_garminconnect_account(user_id, token, db)


def unlink_garminconnect_account(user_id: int, db: Session) -> None:
    """Clear a user's Garmin Connect token and gear sync preference; the caller commits.

    Args:
        user_id: The user unlinking Garmin Connect.
        db: Database session.
    """
    user_integrations_crud.unlink_garminconnect_account(user_id, db)


def unlink_garminconnect_account_if_token(user_id: int, token: dict, db: Session) -> bool:
    """Clear a user's Garmin Connect token only while it is still the given one; the caller commits.

    Args:
        user_id: The user unlinking Garmin Connect.
        token: The stored token that was found to be rejected.
        db: Database session.

    Returns:
        True when the account was unlinked, False when the token has since changed.
    """
    return user_integrations_crud.unlink_garminconnect_account_if_token(user_id, token, db)


def replace_garminconnect_token_if_token(user_id: int, old_token: dict, new_token: dict, db: Session) -> bool:
    """Store a refreshed Garmin Connect token only while the stored one is still ``old_token``; the caller commits.

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
