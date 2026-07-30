"""CRUD operations for OAuth state (PKCE, nonce, replay prevention)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import CursorResult, select
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.sessions.models as auth_sessions_models


@core_decorators.handle_db_errors
def get_oauth_state_by_id_and_not_used(state_id: str, db: Session) -> oauth_state_models.OAuthState | None:
    """Retrieve an OAuth state by ID, validating it is not expired or used.

    Args:
        state_id: The state parameter to lookup.
        db: SQLAlchemy database session.

    Returns:
        The matching OAuthState if valid (not expired and unused),
        None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(oauth_state_models.OAuthState).where(
        oauth_state_models.OAuthState.id == state_id,
        oauth_state_models.OAuthState.used.is_(False),
        oauth_state_models.OAuthState.expires_at > datetime.now(UTC),
    )
    oauth_state = db.execute(stmt).scalar_one_or_none()

    if not oauth_state:
        core_logger.print_to_log(f"OAuth state invalid or expired: {state_id[:8]}...", "warning")

    return oauth_state


@core_decorators.handle_db_errors
def get_oauth_state_by_id(state_id: str, db: Session) -> oauth_state_models.OAuthState | None:
    """Retrieve an OAuth state by ID without validity checks.

    Args:
        state_id: The state parameter to lookup.
        db: SQLAlchemy database session.

    Returns:
        The matching OAuthState if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(oauth_state_models.OAuthState).where(oauth_state_models.OAuthState.id == state_id)
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_oauth_state_by_id_not_expired(state_id: str, db: Session) -> oauth_state_models.OAuthState | None:
    """Retrieve an OAuth state by ID if it is still unexpired.

    Args:
        state_id: The state parameter to lookup.
        db: SQLAlchemy database session.

    Returns:
        The matching OAuthState if found and unexpired,
        None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(oauth_state_models.OAuthState).where(
        oauth_state_models.OAuthState.id == state_id,
        oauth_state_models.OAuthState.expires_at > datetime.now(UTC),
    )
    oauth_state = db.execute(stmt).scalar_one_or_none()

    if not oauth_state:
        core_logger.print_to_log(
            f"OAuth state invalid or expired: {state_id[:8]}...",
            "warning",
        )

    return oauth_state


@core_decorators.handle_db_errors
def get_oauth_state_by_session_id(session_id: str, db: Session) -> oauth_state_models.OAuthState | None:
    """Retrieve an OAuth state via the session relationship.

    Used during token exchange to retrieve stored PKCE challenge
    and other OAuth metadata linked to a user session.

    Args:
        session_id: The session ID to lookup.
        db: SQLAlchemy database session.

    Returns:
        The linked OAuthState if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(auth_sessions_models.UsersSessions).where(auth_sessions_models.UsersSessions.id == session_id)
    session = db.execute(stmt).scalar_one_or_none()

    if not session or not session.oauth_state_id:
        return None

    return get_oauth_state_by_id(session.oauth_state_id, db)


@core_decorators.handle_db_errors
def create_oauth_state(
    db: Session,
    state_id: str,
    nonce: str,
    client_type: str,
    ip_address: str | None,
    idp_id: int | None = None,
    redirect_path: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    user_id: int | None = None,
) -> oauth_state_models.OAuthState:
    """Create and persist a new OAuth state with a 10-minute expiry.

    Args:
        db: SQLAlchemy database session.
        state_id: The state parameter (secrets.token_urlsafe(32)).
        nonce: OIDC nonce for ID token validation.
        client_type: Client type (web or mobile).
        ip_address: Client IP address for validation.
        idp_id: Identity provider ID (may be null if mobile logic).
        redirect_path: Frontend path after login.
        code_challenge: PKCE challenge (required for mobile).
        code_challenge_method: PKCE method (S256).
        user_id: User ID for link mode.

    Returns:
        The persisted OAuthState instance.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    expires_at = datetime.now(UTC) + timedelta(minutes=10)

    oauth_state = oauth_state_models.OAuthState(
        id=state_id,
        idp_id=idp_id,
        nonce=nonce,
        client_type=client_type,
        ip_address=ip_address,
        redirect_path=redirect_path,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        user_id=user_id,
        expires_at=expires_at,
        used=False,
    )

    db.add(oauth_state)
    db.commit()
    db.refresh(oauth_state)

    core_logger.print_to_log(
        f"OAuth state created: {state_id[:8]}... for IdP {idp_id}, client_type={client_type}",
        "debug",
    )

    return oauth_state


@core_decorators.handle_db_errors
def mark_oauth_state_used(state_id: str, db: Session) -> bool:
    """Atomically mark an unused, unexpired OAuth state as used.

    Performs a single conditional UPDATE so concurrent attempts to
    consume the same state cannot both succeed (replay protection).

    Args:
        state_id: The state parameter to mark as used.
        db: SQLAlchemy database session.

    Returns:
        True if exactly one row was claimed, False if the state was
        missing, expired, or already consumed.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    stmt = (
        sa_update(oauth_state_models.OAuthState)
        .where(
            oauth_state_models.OAuthState.id == state_id,
            oauth_state_models.OAuthState.used.is_(False),
            oauth_state_models.OAuthState.expires_at > datetime.now(UTC),
        )
        .values(used=True)
    )
    result: CursorResult[Any] = db.execute(stmt)
    db.commit()

    claimed = result.rowcount == 1
    if claimed:
        core_logger.print_to_log(f"OAuth state marked as used: {state_id[:8]}...", "debug")
    else:
        core_logger.print_to_log(
            f"Cannot mark OAuth state used (missing/expired/replay): {state_id[:8]}...",
            "warning",
        )
    return claimed


@core_decorators.handle_db_errors
def delete_oauth_state(oauth_state_id: str, db: Session) -> int:
    """Delete a single OAuth state by ID.

    Args:
        oauth_state_id: The OAuth state ID to delete.
        db: SQLAlchemy database session.

    Returns:
        Number of OAuth states deleted (0 or 1).

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    stmt = sa_delete(oauth_state_models.OAuthState).where(oauth_state_models.OAuthState.id == oauth_state_id)
    result: CursorResult[Any] = db.execute(stmt)
    db.commit()
    return result.rowcount


@core_decorators.handle_db_errors
def delete_expired_oauth_states(db: Session) -> int:
    """Delete OAuth states past their expiry timestamp.

    Should be called every 5 minutes via background task.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Number of OAuth states deleted.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    stmt = sa_delete(oauth_state_models.OAuthState).where(oauth_state_models.OAuthState.expires_at < datetime.now(UTC))
    result: CursorResult[Any] = db.execute(stmt)
    db.commit()

    deleted_count = result.rowcount
    if deleted_count > 0:
        core_logger.print_to_log(f"Deleted {deleted_count} expired OAuth state(s)", "debug")
    return deleted_count
