"""OAuth state utility functions for cleanup and maintenance."""

from core.database import SessionLocal

import auth.oauth_state.crud as oauth_state_crud

import core.logger as core_logger


def delete_expired_oauth_states_from_db() -> None:
    """
    Remove expired OAuth states from the database.

    Opens a new database session, calls the oauth_state_crud layer to
    delete any expired OAuth states (older than 10 minutes), and logs
    the number of deleted states if one or more were removed.

    This function is designed to be run as a scheduled task every 5 minutes
    to clean up stale OAuth flow state that was never completed or consumed.

    Behavior:
        - Invokes oauth_state_crud.delete_expired_oauth_states(db),
          which returns the number of deleted states (int).
        - If the returned count is greater than zero, logs an informational
          message via core_logger.print_to_log.
        - Always closes the database session via context manager.

    Returns:
        None

    Notes:
        - This function performs destructive, persistent changes (deletions)
          and is intended to be run as part of maintenance.
        - The operation is idempotent: running it repeatedly when there
          are no expired states will have no further effect.
        - OAuth states expire after 10 minutes (set during creation).
    """
    with SessionLocal() as db:
        num_deleted = oauth_state_crud.delete_expired_oauth_states(db)

        if num_deleted > 0:
            core_logger.print_to_log(
                f"Deleted {num_deleted} expired OAuth states from database", "info"
            )
