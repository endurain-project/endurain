"""CRUD operations for user sessions."""

from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import auth.oauth_state.models as oauth_state_models
import auth.oauth_state.crud as oauth_state_crud
import session.models as session_models
import session.schema as session_schema
import session.rotated_refresh_tokens.crud as rotated_tokens_crud

import core.logger as core_logger


class SessionNotFoundError(Exception):
    """
    Exception raised when a requested session cannot be found.

    This error is typically used to indicate that an operation requiring a session
    failed because the session does not exist in the data store.

    Attributes:
        message (str): Optional explanation of the error.
    """


def get_user_sessions(user_id: int, db: Session) -> list[session_models.UsersSessions]:
    """
    Retrieve all session records for a given user, ordered by creation date descending.

    Args:
        user_id (int): The ID of the user whose sessions are to be retrieved.
        db (Session): SQLAlchemy database session.

    Returns:
        list[session_models.UsersSessions]: List of session objects for the user, ordered by most recent.
        None: If no sessions are found for the user.

    Raises:
        HTTPException: If an error occurs during retrieval, raises a 500 Internal Server Error.
    """
    try:
        return (
            db.query(session_models.UsersSessions)
            .filter(session_models.UsersSessions.user_id == user_id)
            .order_by(session_models.UsersSessions.created_at.desc())
            .all()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_user_sessions: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve sessions",
        ) from err


def get_session_by_id(
    session_id: str, db: Session
) -> session_models.UsersSessions | None:
    """
    Retrieve a user session from the database using a refresh token, ensuring the session is not expired.

    Args:
        hashed_refresh_token (str): The hashed refresh token associated with the user session.
        db (Session): The SQLAlchemy database session.

    Returns:
        UsersSessions | None: The user session object if found and not expired, otherwise None.

    Raises:
        HTTPException: If an error occurs during retrieval, raises a 500 Internal Server Error.
    """
    try:
        # Get the session from the database, ensure it's not expired
        return (
            db.query(session_models.UsersSessions)
            .filter(session_models.UsersSessions.id == session_id)
            .filter(
                session_models.UsersSessions.expires_at > datetime.now(timezone.utc)
            )
            .first()
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_session_by_id: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session",
        ) from err


def get_session_with_oauth_state(
    session_id: str, db: Session
) -> tuple[session_models.UsersSessions, oauth_state_models.OAuthState | None] | None:
    """
    Retrieve a session with its associated OAuthState for token exchange validation.

    This function performs a query to retrieve a session along with its
    linked OAuth state record (if any). Used during mobile token exchange to
    validate PKCE and ensure the session is valid.

    Args:
        session_id (str): The unique identifier of the session.
        db (Session): The SQLAlchemy database session.

    Returns:
        tuple[UsersSessions, OAuthState | None] | None: A tuple of (session, oauth_state)
            where oauth_state may be None if not linked. Returns None if session not found.

    Raises:
        HTTPException: If an error occurs during retrieval (500).
    """
    try:
        # Query session
        db_session = (
            db.query(session_models.UsersSessions)
            .filter(session_models.UsersSessions.id == session_id)
            .filter(
                session_models.UsersSessions.expires_at > datetime.now(timezone.utc)
            )
            .first()
        )

        if not db_session:
            return None

        # Get OAuth state if linked
        oauth_state = None
        if db_session.oauth_state_id:
            oauth_state = (
                db.query(oauth_state_models.OAuthState)
                .filter(oauth_state_models.OAuthState.id == db_session.oauth_state_id)
                .first()
            )

        return (db_session, oauth_state)
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_session_with_oauth_state: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session with OAuth state",
        ) from err


def create_session(
    session: session_schema.UsersSessions, db: Session
) -> session_models.UsersSessions:
    """
    Creates a new user session in the database.

    Args:
        session (session_schema.UsersSessions): The session data to be created.
        db (Session): The SQLAlchemy database session.

    Returns:
        session_models.UsersSessions: The newly created session object.

    Raises:
        HTTPException: If an error occurs during session creation, raises a 500 Internal Server Error.
    """
    try:
        # Create a new session using model_dump
        db_session = session_models.UsersSessions(**session.model_dump())

        # Add the session to the database
        db.add(db_session)
        db.commit()
        db.refresh(db_session)

        # Return the session
        return db_session
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in create_session: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session",
        ) from err


def mark_tokens_exchanged(session_id: str, db: Session) -> None:
    """
    Atomically mark tokens as exchanged for a session to prevent duplicate mobile token exchanges.

    This function sets the tokens_exchanged flag to True for a specific session,
    clears the oauth_state_id reference, and deletes the associated OAuth state.
    Prevents replay attacks where multiple token exchange requests could be made
    for the same session.

    Per OAuth 2.1 best practices, the OAuth state parameter is ephemeral and should
    be deleted immediately after successful token exchange. The session maintains
    its own security mechanisms (refresh tokens, CSRF tokens) independently.

    Args:
        session_id (str): The unique identifier of the session.
        db (Session): The SQLAlchemy database session.

    Raises:
        SessionNotFoundError: If the session does not exist.
        HTTPException: If an error occurs during the update (500).
    """
    try:
        # Get the session from the database
        db_session = (
            db.query(session_models.UsersSessions)
            .filter(session_models.UsersSessions.id == session_id)
            .first()
        )

        # Check if the session exists
        if not db_session:
            raise SessionNotFoundError(f"Session {session_id} not found")

        # Store oauth_state_id before clearing (for cleanup)
        oauth_state_id_to_delete = db_session.oauth_state_id

        # Mark tokens as exchanged and clear OAuth state reference
        # Per OAuth 2.1: state is ephemeral, only needed during authorization flow
        db_session.tokens_exchanged = True
        db_session.oauth_state_id = None
        db.commit()

        # Delete the OAuth state now that tokens are exchanged
        # The state has served its CSRF protection purpose
        if oauth_state_id_to_delete:
            try:
                oauth_state_crud.delete_oauth_state(oauth_state_id_to_delete, db)
            except Exception as err:
                # Log but don't fail - cleanup job will handle orphaned states
                core_logger.print_to_log(
                    f"Failed to delete OAuth state {oauth_state_id_to_delete[:8]}... "
                    f"after token exchange: {err}",
                    "warning",
                    exc=err,
                )
    except SessionNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in mark_tokens_exchanged: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark tokens as exchanged",
        ) from err


def edit_session(session: session_schema.UsersSessions, db: Session) -> None:
    """
    Edits an existing user session in the database.

    This function retrieves a session by its ID, updates its fields with the provided values,
    and commits the changes to the database. If the session does not exist, it raises a 404 error.
    If any other exception occurs, it rolls back the transaction, logs the error, and raises a 500 error.

    Args:
        session (session_schema.UsersSessions): The session data containing updated fields.
        db (Session): The SQLAlchemy database session.

    Raises:
        HTTPException: If the session is not found (404) or if an error occurs during update (500).
    """
    try:
        # Get the session from the database
        db_session = (
            db.query(session_models.UsersSessions)
            .filter(session_models.UsersSessions.id == session.id)
            .first()
        )

        # Check if the session exists, if not raises exception
        if not db_session:
            raise SessionNotFoundError(f"Session {session.id} not found")

        # Dictionary of the fields to update if they are not None
        session_data = session.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_session dynamically
        for key, value in session_data.items():
            setattr(db_session, key, value)

        # Commit the transaction
        db.commit()
    except SessionNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in edit_session: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update session",
        ) from err


def delete_session(session_id: str, user_id: int, db: Session) -> None:
    """
    Deletes a user session from the database.

    Args:
        session_id (str): The unique identifier of the session to delete.
        user_id (int): The ID of the user associated with the session.
        db (Session): The SQLAlchemy database session.

    Raises:
        HTTPException: If the session is not found (404) or if an error occurs during deletion (500).

    Notes:
        - Deletes rotated tokens associated with the session before deleting the session
        - Rolls back the transaction and logs the error if an unexpected exception occurs.
        - Commits the transaction if the session is successfully deleted.
    """
    try:
        # Get the session to retrieve token_family_id before deletion
        session = (
            db.query(session_models.UsersSessions)
            .filter(
                session_models.UsersSessions.id == session_id,
                session_models.UsersSessions.user_id == user_id,
            )
            .first()
        )

        # Check if the session was found
        if session is None:
            raise SessionNotFoundError(
                f"Session {session_id} not found for user {user_id}"
            )

        # Store oauth_state_id before deleting session (if exists)
        oauth_state_id_to_delete = session.oauth_state_id

        # Delete rotated tokens for this session's family (foreign key constraint)
        rotated_tokens_crud.delete_by_family(session.token_family_id, db)

        # Delete the session
        num_deleted = (
            db.query(session_models.UsersSessions)
            .filter(
                session_models.UsersSessions.id == session_id,
                session_models.UsersSessions.user_id == user_id,
            )
            .delete()
        )

        # Delete OAuth state after session is deleted if exists
        if oauth_state_id_to_delete:
            oauth_state_crud.delete_oauth_state(oauth_state_id_to_delete, db)

        # Commit the transaction
        db.commit()
    except SessionNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in delete_session: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete session",
        ) from err


def delete_idle_sessions(cutoff_time: datetime, db: Session) -> int:
    """
    Delete sessions that have exceeded the idle timeout threshold.

    This function removes all sessions where the last_activity_at timestamp
    is older than the provided cutoff time. Used by the cleanup scheduler
    to periodically remove inactive sessions.

    Args:
        cutoff_time (datetime): Sessions with last_activity_at before this time will be deleted.
        db (Session): The SQLAlchemy database session.

    Returns:
        int: The number of sessions deleted.

    Raises:
        HTTPException: If an error occurs during deletion (500).
    """
    try:
        # Delete sessions with last_activity_at older than cutoff_time
        num_deleted = (
            db.query(session_models.UsersSessions)
            .filter(session_models.UsersSessions.last_activity_at < cutoff_time)
            .delete()
        )

        # Commit the transaction
        db.commit()

        return num_deleted
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in delete_idle_sessions: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete idle sessions",
        ) from err


def delete_sessions_by_family(token_family_id: str, db: Session) -> int:
    """
    Delete all sessions belonging to a token family.

    Args:
        token_family_id: The family ID to delete sessions for.
        db: The SQLAlchemy database session.

    Returns:
        Number of sessions deleted.

    Raises:
        HTTPException: If an error occurs during deletion (500).
    """
    try:
        num_deleted = (
            db.query(session_models.UsersSessions)
            .filter(session_models.UsersSessions.token_family_id == token_family_id)
            .delete()
        )

        db.commit()
        return num_deleted
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in delete_sessions_by_family: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete sessions by family",
        ) from err
