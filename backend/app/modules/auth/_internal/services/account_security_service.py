"""Auth-owned account security workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger
import modules.auth._internal.security_stores as auth_security_stores
import modules.auth._internal.services.step_up_service as step_up_service
import modules.auth.password_policy as auth_password_policy
import modules.auth.sessions.crud as auth_sessions_crud
import modules.auth.sessions.schema as auth_sessions_schema
import modules.server_settings.utils as server_settings_utils
import modules.users.users.schema as users_schema
import modules.users.users.utils as users_utils

if TYPE_CHECKING:
    from modules.auth.identity_service import IdentityService


def get_user_sessions(
    token_user_id: int,
    db: Session,
) -> list[auth_sessions_schema.UsersSessionsRead]:
    """Retrieve active sessions for the authenticated user."""
    if core_config.settings.ENVIRONMENT == "demo":
        core_logger.print_to_log(
            "Session retrieval attempted in demo environment - returning empty list",
            "info",
        )
        return []

    return auth_sessions_crud.get_user_sessions(token_user_id, db)


def delete_user_session(
    session_id: str,
    token_user_id: int,
    db: Session,
) -> None:
    """Delete one authenticated user's session."""
    auth_sessions_crud.delete_session(session_id, token_user_id, db)


def delete_other_user_sessions(
    token_user_id: int,
    current_session_id: str,
    db: Session,
) -> int:
    """Revoke all of the user's sessions except their current one.

    Backs the self-service "sign out other devices" action: every
    session the user owns is deleted except ``current_session_id``
    (the caller's own session, derived from their access token), so
    the caller stays signed in while every other device is evicted.

    Args:
        token_user_id: ID of the authenticated user.
        current_session_id: The caller's current session, preserved.
        db: SQLAlchemy session.

    Returns:
        Number of sessions revoked.
    """
    revoked = auth_sessions_crud.delete_sessions_by_user(
        token_user_id,
        db,
        exclude_session_id=current_session_id,
    )
    core_logger.print_to_log(
        f"User {token_user_id} revoked {revoked} other session(s)",
        "info",
    )
    return revoked


def change_own_password(
    user_id: int,
    current_password: str,
    new_password: str,
    mfa_code: str | None,
    identity_service: IdentityService,
    step_up_store: auth_security_stores.StepUpStore,
    db: Session,
    revoke_other_sessions: bool = False,
    current_session_id: str | None = None,
) -> None:
    """
    Change a user's own password after step-up verification.

    Args:
        user_id: ID of the authenticated user.
        current_password: Current password supplied for step-up.
        new_password: New plaintext password to store.
        mfa_code: Optional MFA code supplied for step-up.
        identity_service: Identity service dependency.
        step_up_store: Step-up lockout store.
        db: SQLAlchemy session.
        revoke_other_sessions: When True, delete all of the user's
            other sessions (keeping ``current_session_id``) so a
            password change can evict a suspected attacker.
        current_session_id: Session ID of the caller, preserved when
            ``revoke_other_sessions`` is True so the caller is not
            logged out.

    Returns:
        None.

    Raises:
        HTTPException: If step-up verification or persistence fails.
    """
    step_up_service.verify_step_up_credentials(
        user_id,
        current_password,
        mfa_code,
        identity_service,
        step_up_store,
        db,
    )

    server_settings = server_settings_utils.get_server_settings_or_404(db)
    db_user = users_utils.get_user_by_id_or_404(user_id, db)
    access_type = users_schema.normalize_access_type(db_user.access_type)
    hashed_password = auth_password_policy.validate_and_hash_for_user(
        identity_service,
        server_settings,
        access_type,
        new_password,
    )
    identity_service.set_local_password_hash(user_id, hashed_password)
    auth_security_stores.clear_pending_mfa_for_user(user_id)

    if revoke_other_sessions:
        revoked = auth_sessions_crud.delete_sessions_by_user(
            user_id,
            db,
            exclude_session_id=current_session_id,
        )
        core_logger.print_to_log(
            f"User {user_id} revoked {revoked} other session(s) after password change",
            "info",
        )

    core_logger.print_to_log(
        f"User {user_id} changed password (step-up verified)",
        "info",
    )


def change_managed_user_password(
    user_id: int,
    new_password: str,
    identity_service: IdentityService,
    db: Session,
) -> None:
    """
    Change a managed user's password and revoke auth state.

    Args:
        user_id: ID of the user whose password is changed.
        new_password: New plaintext password to store.
        identity_service: Identity service dependency.
        db: SQLAlchemy session.

    Returns:
        None.

    Raises:
        HTTPException: If password persistence fails.
    """
    server_settings = server_settings_utils.get_server_settings_or_404(db)
    db_user = users_utils.get_user_by_id_or_404(user_id, db)
    access_type = users_schema.normalize_access_type(db_user.access_type)
    hashed_password = auth_password_policy.validate_and_hash_for_user(
        identity_service,
        server_settings,
        access_type,
        new_password,
    )
    identity_service.set_local_password_hash(user_id, hashed_password)
    auth_sessions_crud.delete_sessions_by_user(user_id, db)
    auth_security_stores.clear_pending_mfa_for_user(user_id)
