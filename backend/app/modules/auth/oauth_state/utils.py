"""OAuth state utility functions for cleanup and maintenance."""

import secrets

import core.logger as core_logger
import modules.auth.oauth_state.crud as oauth_state_crud
from core.database import SessionLocal


def create_state_id_and_nonce() -> tuple[str, str]:
    """Generate a new random state ID and nonce for OAuth flows.

    Returns:
        Tuple of (state_id, nonce), both URL-safe random 32-byte tokens.
    """
    state_id = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    return state_id, nonce


def delete_expired_oauth_states_from_db() -> None:
    """Remove expired OAuth states from the database.

    Opens a new database session and delegates deletion to the CRUD
    layer. Intended to be invoked by the scheduler every 5 minutes
    to clean up stale OAuth flow state that was never completed
    or consumed (states expire 10 minutes after creation).

    Returns:
        None.
    """
    with SessionLocal() as db:
        num_deleted = oauth_state_crud.delete_expired_oauth_states(db)

        if num_deleted > 0:
            core_logger.print_to_log(
                f"Deleted {num_deleted} expired OAuth states from database",
                "info",
            )
