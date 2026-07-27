"""CRUD operations for user sessions."""

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import CursorResult, delete, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.auth.oauth_state.crud as oauth_state_crud
import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.sessions.models as auth_sessions_models
import modules.auth.sessions.rotated_refresh_tokens.crud as auth_sessions_rotated_tokens_crud
import modules.auth.sessions.schema as auth_sessions_schema

logger = core_logger.get_logger(__name__)


@core_decorators.handle_db_errors
def get_user_sessions(
    user_id: int,
    db: Session,
) -> list[auth_sessions_models.UsersSessions]:
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
        select(auth_sessions_models.UsersSessions)
        .where(auth_sessions_models.UsersSessions.user_id == user_id)
        .order_by(auth_sessions_models.UsersSessions.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


@core_decorators.handle_db_errors
def get_session_by_id(
    session_id: str,
    db: Session,
) -> auth_sessions_models.UsersSessions | None:
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
    stmt = select(auth_sessions_models.UsersSessions).where(auth_sessions_models.UsersSessions.id == session_id)
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_session_by_id_not_expired(
    session_id: str,
    db: Session,
) -> auth_sessions_models.UsersSessions | None:
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
        select(auth_sessions_models.UsersSessions)
        .where(auth_sessions_models.UsersSessions.id == session_id)
        .where(auth_sessions_models.UsersSessions.expires_at > datetime.now(UTC))
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_session_with_oauth_state(
    session_id: str,
    db: Session,
) -> (
    tuple[
        auth_sessions_models.UsersSessions,
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
        select(auth_sessions_models.UsersSessions)
        .where(auth_sessions_models.UsersSessions.id == session_id)
        .where(auth_sessions_models.UsersSessions.expires_at > datetime.now(UTC))
    )
    db_session = db.execute(stmt).scalar_one_or_none()

    if not db_session:
        return None

    # Get OAuth state if linked
    oauth_state = None
    if db_session.oauth_state_id:
        oauth_state = oauth_state_crud.get_oauth_state_by_id_not_expired(db_session.oauth_state_id, db)

    return (db_session, oauth_state)


@core_decorators.handle_db_errors
def create_session(
    session: auth_sessions_schema.UsersSessionsInternal,
    db: Session,
) -> auth_sessions_models.UsersSessions:
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
    db_session = auth_sessions_models.UsersSessions(**session.model_dump())
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


@core_decorators.handle_db_errors
def set_session_refresh_token_hash(
    session_id: str, hashed_refresh_token: str, db: Session
) -> auth_sessions_models.UsersSessions:
    """
    Persist a hashed refresh token on a session.

    Used by the SSO token-exchange flow to record the freshly minted
    refresh token (already hashed) on the session row.

    Args:
        session_id: The unique identifier of the session.
        hashed_refresh_token: The hashed refresh token to store.
        db: SQLAlchemy database session.

    Returns:
        The updated session object.

    Raises:
        HTTPException: If session not found (404) or database error
            occurs (500).
    """
    db_session = get_session_by_id(session_id, db)

    if not db_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    db_session.refresh_token = hashed_refresh_token
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
            logger.debug(f"Deleted OAuth state {oauth_state_id_to_delete[:8]}... after token exchange")
        except Exception as err:
            # Log but don't fail - cleanup job handles orphaned
            # states
            logger.warning(
                f"Failed to delete OAuth state {oauth_state_id_to_delete[:8]}... after token exchange: {err}",
                exc_info=err,
            )


@core_decorators.handle_db_errors
def claim_session_for_token_exchange(
    session_id: str,
    hashed_refresh_token: str,
    db: Session,
) -> bool:
    """
    Atomically claim a session for one-shot PKCE token exchange.

    Performs a single conditional UPDATE that simultaneously
    flips ``tokens_exchanged`` to ``True`` and stores the freshly
    minted, hashed refresh token — but only if the session is
    still in the ``tokens_exchanged = False`` state. This closes
    the check-then-act race that the previous read-then-write
    sequence allowed: two concurrent exchanges with the same
    ``code_verifier`` could both pass an ``if not
    tokens_exchanged`` guard and both write a refresh token,
    handing one caller a working token while invalidating the
    other.

    Args:
        session_id: The session to claim.
        hashed_refresh_token: The (Argon2-hashed) refresh token
            to persist on the row.
        db: SQLAlchemy database session.

    Returns:
        True if exactly one row was claimed (the caller owns the
        exchange). False if the session was missing or already
        exchanged — caller should respond with 409 Conflict.

    Raises:
        HTTPException: 500 if the database operation fails.
    """
    stmt = (
        sa_update(auth_sessions_models.UsersSessions)
        .where(
            auth_sessions_models.UsersSessions.id == session_id,
            auth_sessions_models.UsersSessions.tokens_exchanged.is_(False),
        )
        .values(
            tokens_exchanged=True,
            refresh_token=hashed_refresh_token,
        )
    )
    result: CursorResult[Any] = db.execute(stmt)
    db.commit()

    claimed = result.rowcount == 1
    if not claimed:
        logger.warning(f"Token exchange claim lost race for session {session_id[:8]}... (missing or already exchanged)")
        return False

    # Best-effort OAuth state cleanup mirrors mark_tokens_exchanged.
    db_session = get_session_by_id(session_id, db)
    if db_session and db_session.oauth_state_id:
        oauth_state_id_to_delete = db_session.oauth_state_id
        db_session.oauth_state_id = None
        db.commit()
        try:
            oauth_state_crud.delete_oauth_state(oauth_state_id_to_delete, db)
        except Exception as err:
            logger.warning(
                f"Failed to delete OAuth state {oauth_state_id_to_delete[:8]}... after token exchange: {err}",
                exc_info=err,
            )

    return True


@core_decorators.handle_db_errors
def edit_session(
    session: auth_sessions_schema.UsersSessionsInternal,
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
def update_session_csrf_hash(
    session_id: str,
    csrf_token_hash: str,
    db: Session,
) -> None:
    """
    Update only the CSRF token hash on an existing session.

    Used by the in-grace refresh replay path, which mints a fresh
    CSRF token for web clients without rotating the refresh token
    or bumping the rotation count.

    Args:
        session_id: The session to update.
        csrf_token_hash: New HMAC-SHA256 CSRF token hash.
        db: SQLAlchemy database session.

    Raises:
        HTTPException: If session not found (404) or database
            error occurs (500).
    """
    db_session = get_session_by_id(session_id, db)

    if not db_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    db_session.csrf_token_hash = csrf_token_hash
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
    stmt = select(auth_sessions_models.UsersSessions).where(
        auth_sessions_models.UsersSessions.id == session_id,
        auth_sessions_models.UsersSessions.user_id == user_id,
    )
    session = db.execute(stmt).scalar_one_or_none()

    # Check if the session was found
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(f"Session {session_id} not found for user {user_id}"),
        )

    # Store oauth_state_id before deleting session (if exists)
    oauth_state_id_to_delete = session.oauth_state_id

    # Delete rotated tokens for this session's family
    auth_sessions_rotated_tokens_crud.delete_by_family(session.token_family_id, db)

    # Delete the session
    stmt = delete(auth_sessions_models.UsersSessions).where(
        auth_sessions_models.UsersSessions.id == session_id,
        auth_sessions_models.UsersSessions.user_id == user_id,
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
    stmt = delete(auth_sessions_models.UsersSessions).where(
        auth_sessions_models.UsersSessions.last_activity_at < cutoff_time
    )
    result: CursorResult[Any] = db.execute(stmt)
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
    stmt = delete(auth_sessions_models.UsersSessions).where(
        auth_sessions_models.UsersSessions.token_family_id == token_family_id
    )
    result: CursorResult[Any] = db.execute(stmt)
    db.commit()
    return result.rowcount


@core_decorators.handle_db_errors
def delete_sessions_by_user(
    user_id: int,
    db: Session,
    commit: bool = True,
    exclude_session_id: str | None = None,
) -> int:
    """
    Delete all sessions for a user.

    Args:
        user_id: The ID of the user whose sessions should be
            deleted.
        db: SQLAlchemy database session.
        commit: Whether to commit the session deletion immediately.
        exclude_session_id: When provided, this session is left
            intact (e.g. the caller's current session so it is
            not logged out by a "revoke other sessions" action).

    Returns:
        Number of sessions deleted.

    Raises:
        HTTPException: If database error occurs.
    """
    stmt = delete(auth_sessions_models.UsersSessions).where(auth_sessions_models.UsersSessions.user_id == user_id)
    if exclude_session_id is not None:
        stmt = stmt.where(auth_sessions_models.UsersSessions.id != exclude_session_id)
    result = db.execute(stmt)
    if commit:
        db.commit()
    return result.rowcount
