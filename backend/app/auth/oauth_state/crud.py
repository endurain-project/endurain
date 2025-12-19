from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

import auth.oauth_state.models as oauth_state_models
import session.models as session_models

import core.logger as core_logger


def get_oauth_state_by_id(
    state_id: str, db: Session
) -> oauth_state_models.OAuthState | None:
    """
    Get OAuth state by ID, validate not expired/used.

    Args:
        db: Database session.
        state_id: The state parameter to lookup.

    Returns:
        oauth_state_models.OAuthState if valid and not expired, else None.
    """
    oauth_state = (
        db.query(oauth_state_models.OAuthState)
        .filter(oauth_state_models.OAuthState.id == state_id)
        .first()
    )

    if not oauth_state:
        core_logger.print_to_log(f"OAuth state not found: {state_id[:8]}...", "warning")
        return None

    # Check expiry
    if datetime.now(timezone.utc) > oauth_state.expires_at:
        core_logger.print_to_log(f"OAuth state expired: {state_id[:8]}...", "warning")
        return None

    # Check if already used
    if oauth_state.used:
        core_logger.print_to_log(
            f"OAuth state already used (replay attempt?): " f"{state_id[:8]}...",
            "warning",
        )
        return None

    return oauth_state


def get_oauth_state_by_session_id(
    db: Session,
    session_id: str,
) -> oauth_state_models.OAuthState | None:
    """
    Lookup OAuth state via session relationship.

    Used during token exchange to retrieve stored PKCE
    challenge and other OAuth metadata.

    Args:
        db: Database session.
        session_id: The session ID to lookup.

    Returns:
        oauth_state_models.OAuthState if found and linked, else None.
    """
    session = (
        db.query(session_models.UsersSessions)
        .filter(session_models.UsersSessions.id == session_id)
        .first()
    )

    if not session:
        return None

    if not session.oauth_state_id:
        return None

    oauth_state = (
        db.query(oauth_state_models.OAuthState)
        .filter(oauth_state_models.OAuthState.id == session.oauth_state_id)
        .first()
    )

    return oauth_state


def create_oauth_state(
    db: Session,
    state_id: str,
    idp_id: int,
    nonce: str,
    client_type: str,
    ip_address: str | None,
    redirect_path: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    user_id: int | None = None,
) -> oauth_state_models.OAuthState:
    """
    Create new OAuth state with 10-minute expiry.

    Args:
        db: Database session.
        state_id: The state parameter (secrets.token_urlsafe(32)).
        idp_id: Identity provider ID.
        nonce: OIDC nonce for ID token validation.
        client_type: Client type (web or mobile).
        ip_address: Client IP address for validation.
        redirect_path: Frontend path after login.
        code_challenge: PKCE challenge (required for mobile).
        code_challenge_method: PKCE method (S256).
        user_id: User ID for link mode.

    Returns:
        Created oauth_state_models.OAuthState object.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

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
        f"OAuth state created: {state_id[:8]}... "
        f"for IdP {idp_id}, client_type={client_type}",
        "debug",
    )

    return oauth_state


def mark_oauth_state_used(
    db: Session,
    state_id: str,
) -> oauth_state_models.OAuthState | None:
    """
    Atomically mark OAuth state as used (prevents replay).

    Args:
        db: Database session.
        state_id: The state parameter to mark.

    Returns:
        Updated oauth_state_models.OAuthState if successful, else None.

    Raises:
        Does not raise. Returns None if state not found.
    """
    oauth_state = (
        db.query(oauth_state_models.OAuthState)
        .filter(oauth_state_models.OAuthState.id == state_id)
        .first()
    )

    if not oauth_state:
        core_logger.print_to_log(
            f"Cannot mark OAuth state used: not found " f"{state_id[:8]}...", "warning"
        )
        return None

    # Mark as used atomically
    oauth_state.used = True
    db.commit()
    db.refresh(oauth_state)

    core_logger.print_to_log(f"OAuth state marked as used: {state_id[:8]}...", "debug")

    return oauth_state


def delete_oauth_state(oauth_state_id: str, db: Session) -> int:
    """
    Delete OAuth state for a specific OAuth state ID.

    Args:
        oauth_state_id: The OAuth state ID to delete tokens for.
        db: Database session.

    Returns:
        Number of OAuth states deleted.

    Raises:
        HTTPException: If an error occurs during deletion (500).
    """
    try:
        num_deleted = (
            db.query(oauth_state_models.OAuthState)
            .filter(oauth_state_models.OAuthState.id == oauth_state_id)
            .delete()
        )

        db.commit()
        return num_deleted
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in delete_oauth_state: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete OAuth state",
        ) from err


def delete_expired_oauth_states(db: Session) -> int:
    """
    Delete OAuth states older than 10 minutes.

    Should be called every 5 minutes via background task.

    Args:
        db: Database session.

    Returns:
        Number of states deleted.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

    result = (
        db.query(oauth_state_models.OAuthState)
        .filter(oauth_state_models.OAuthState.expires_at < cutoff)
        .delete(synchronize_session=False)
    )

    db.commit()

    if result > 0:
        core_logger.print_to_log(f"Deleted {result} expired OAuth states", "debug")

    return result
