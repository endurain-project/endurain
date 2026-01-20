"""CRUD operations for user sessions."""

from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import auth.oauth_state.models as oauth_state_models
import auth.oauth_state.crud as oauth_state_crud

import users.users_session.models as users_session_models
import users.users_session.schema as users_session_schema

import users.users_session.rotated_refresh_tokens.crud as users_session_rotated_tokens_crud

import core.logger as core_logger
import core.decorators as core_decorators


@core_decorators.handle_db_errors
def get_user_sessions(
    user_id: int,
    db: Session,
) -> list[users_session_models.UsersSessions]:
    """
    Retrieve all sessions for a user, ordered by creation date.

    Args:
        user_id: The ID of the user whose sessions to retrieve.
        db: SQLAlchemy database session.

    Returns:
        List of session objects, ordered by most recent first.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(users_session_models.UsersSessions)
        .where(users_session_models.UsersSessions.user_id == user_id)
        .order_by(users_session_models.UsersSessions.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


@core_decorators.handle_db_errors
def get_session_by_id(
    session_id: str,
    db: Session,
) -> users_session_models.UsersSessions | None:
    """
    Retrieve a user session by ID.

    Args:
        session_id: The unique identifier of the session.
        db: SQLAlchemy database session.

    Returns:
        The session object if found, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = select(users_session_models.UsersSessions).where(
        users_session_models.UsersSessions.id == session_id
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_session_by_id_not_expired(
    session_id: str,
    db: Session,
) -> users_session_models.UsersSessions | None:
    """
    Retrieve a user session by ID if not expired.

    Args:
        session_id: The unique identifier of the session.
        db: SQLAlchemy database session.

    Returns:
        The session object if found and not expired, None otherwise.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = (
        select(users_session_models.UsersSessions)
        .where(users_session_models.UsersSessions.id == session_id)
        .where(
            users_session_models.UsersSessions.expires_at > datetime.now(timezone.utc)
        )
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_session_with_oauth_state(
    session_id: str,
    db: Session,
) -> (
    tuple[
        users_session_models.UsersSessions,
        oauth_state_models.OAuthState | None,
    ]
    | None
):
    """
    Retrieve a session with its OAuth state for token exchange.

    Performs a query to retrieve a session with its linked OAuth
    state record (if any). Used during mobile token exchange to
    validate PKCE and ensure the session is valid.

    Args:
        session_id: The unique identifier of the session.
        db: SQLAlchemy database session.

    Returns:
        Tuple of (session, oauth_state) where oauth_state may be
        None if not linked. Returns None if session not found.

    Raises:
        HTTPException: If database error occurs.
    """
    # Query session
    stmt = (
        select(users_session_models.UsersSessions)
        .where(users_session_models.UsersSessions.id == session_id)
        .where(
            users_session_models.UsersSessions.expires_at > datetime.now(timezone.utc)
        )
    )
    db_session = db.execute(stmt).scalar_one_or_none()

    if not db_session:
        return None

    # Get OAuth state if linked
    oauth_state = None
    if db_session.oauth_state_id:
        oauth_state = oauth_state_crud.get_oauth_state_by_id(
            db_session.oauth_state_id, db
        )

    return (db_session, oauth_state)


@core_decorators.handle_db_errors
def create_session(
    session: users_session_schema.UsersSessionsInternal,
    db: Session,
) -> users_session_models.UsersSessions:
    """
    Create a new user session in the database.

    Args:
        session: The session data to be created.
        db: SQLAlchemy database session.

    Returns:
        The newly created session object.

    Raises:
        HTTPException: If database error occurs.
    """
    db_session = users_session_models.UsersSessions(**session.model_dump())
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


@core_decorators.handle_db_errors
def mark_tokens_exchanged(session_id: str, db: Session) -> None:
    """
    Mark tokens as exchanged and clear OAuth state.

    Sets tokens_exchanged flag to prevent duplicate mobile token
    exchanges. Deletes the associated OAuth state per OAuth 2.1
    best practices (state is ephemeral).

    Args:
        session_id: The unique identifier of the session.
        db: SQLAlchemy database session.

    Raises:
        HTTPException: If session not found (404) or database
            error occurs (500).
    """
    # Get the session from the database
    db_session = get_session_by_id(session_id, db)

    # Check if the session exists
    if not db_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Store oauth_state_id before clearing (for cleanup)
    oauth_state_id_to_delete = db_session.oauth_state_id

    # Mark tokens as exchanged and clear OAuth state reference
    db_session.tokens_exchanged = True
    db_session.oauth_state_id = None
    db.commit()

    # Delete the OAuth state now that tokens are exchanged
    if oauth_state_id_to_delete:
        try:
            oauth_state_crud.delete_oauth_state(oauth_state_id_to_delete, db)
            core_logger.print_to_log(
                f"Deleted OAuth state "
                f"{oauth_state_id_to_delete[:8]}... after token "
                f"exchange",
                "debug",
            )
        except Exception as err:
            # Log but don't fail - cleanup job handles orphaned
            # states
            core_logger.print_to_log(
                f"Failed to delete OAuth state "
                f"{oauth_state_id_to_delete[:8]}... after token "
                f"exchange: {err}",
                "warning",
                exc=err,
            )


@core_decorators.handle_db_errors
def edit_session(
    session: users_session_schema.UsersSessionsInternal,
    db: Session,
) -> None:
    """
    Update an existing user session with new field values.

    Args:
        session: Session data with fields to update.
        db: SQLAlchemy database session.

    Raises:
        HTTPException: If session not found (404) or database
            error occurs (500).
    """
    # Get the session from the database
    db_session = get_session_by_id(session.id, db)

    # Check if the session exists
    if not db_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session.id} not found",
        )

    # Update fields dynamically
    session_data = session.model_dump(exclude_unset=True)
    for key, value in session_data.items():
        setattr(db_session, key, value)

    db.commit()
    db.refresh(db_session)


@core_decorators.handle_db_errors
def delete_session(
    session_id: str,
    user_id: int,
    db: Session,
) -> None:
    """
    Delete a user session and its associated resources.

    Deletes rotated tokens, the session, and any linked OAuth
    state. Used when user explicitly logs out a session.

    Args:
        session_id: The unique identifier of the session to
            delete.
        user_id: The ID of the user associated with the session.
        db: SQLAlchemy database session.

    Raises:
        HTTPException: If session not found (404) or database
            error occurs (500).
    """
    # Get the session to retrieve token_family_id before deletion
    stmt = select(users_session_models.UsersSessions).where(
        users_session_models.UsersSessions.id == session_id,
        users_session_models.UsersSessions.user_id == user_id,
    )
    session = db.execute(stmt).scalar_one_or_none()

    # Check if the session was found
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(f"Session {session_id} not found for user " f"{user_id}"),
        )

    # Store oauth_state_id before deleting session (if exists)
    oauth_state_id_to_delete = session.oauth_state_id

    # Delete rotated tokens for this session's family
    users_session_rotated_tokens_crud.delete_by_family(session.token_family_id, db)

    # Delete the session
    stmt = delete(users_session_models.UsersSessions).where(
        users_session_models.UsersSessions.id == session_id,
        users_session_models.UsersSessions.user_id == user_id,
    )
    db.execute(stmt)

    # Delete OAuth state after session is deleted if exists
    if oauth_state_id_to_delete:
        oauth_state_crud.delete_oauth_state(oauth_state_id_to_delete, db)

    db.commit()


@core_decorators.handle_db_errors
def delete_idle_sessions(
    cutoff_time: datetime,
    db: Session,
) -> int:
    """
    Delete sessions exceeding the idle timeout threshold.

    Removes sessions where last_activity_at is older than the
    cutoff time. Used by cleanup scheduler to remove inactive
    sessions.

    Args:
        cutoff_time: Sessions with last_activity_at before this
            time will be deleted.
        db: SQLAlchemy database session.

    Returns:
        Number of sessions deleted.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = delete(users_session_models.UsersSessions).where(
        users_session_models.UsersSessions.last_activity_at < cutoff_time
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount


@core_decorators.handle_db_errors
def delete_sessions_by_family(
    token_family_id: str,
    db: Session,
) -> int:
    """
    Delete all sessions belonging to a token family.

    Used when token reuse is detected to invalidate entire
    session family as security measure.

    Args:
        token_family_id: The family ID to delete sessions for.
        db: SQLAlchemy database session.

    Returns:
        Number of sessions deleted.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = delete(users_session_models.UsersSessions).where(
        users_session_models.UsersSessions.token_family_id == token_family_id
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount
