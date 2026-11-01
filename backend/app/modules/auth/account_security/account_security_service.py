"""Auth-owned account security workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.i18n as core_i18n
import core.logger as core_logger
import core.pagination as core_pagination
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.email_messages as account_security_email_messages
import modules.auth.account_security.event_publishers as account_security_event_publishers
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.integration_service as identity_providers_integration
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.auth.sessions.schema as auth_sessions_schema
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)

if TYPE_CHECKING:
    import modules.auth.account_security.step_up_store as account_security_step_up_store


def _stage_sessions_revoked(user_id: int, revoked: int, db: Session) -> None:
    """Stage the audit row of several sessions a user lost at once.

    Args:
        user_id: ID of the user whose sessions ended.
        revoked: How many sessions ended.
        db: SQLAlchemy session.
    """
    jasil_audit.stage(
        db,
        account_security_audit_actions.SESSION_REVOKE,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=account_security_audit_actions.SessionsRevokedDetails(sessions_revoked=revoked),
    )


def list_user_sessions(
    token_user_id: int,
    page: core_pagination.PageParams,
    db: Session,
) -> auth_sessions_schema.UsersSessionsPage:
    """Retrieve one page of the authenticated user's sessions."""
    return sessions_integration.list_user_sessions(token_user_id, page, db)


def delete_user_session(
    session_id: str,
    token_user_id: int,
    db: Session,
) -> None:
    """Delete one authenticated user's session."""
    sessions_integration.delete_session(session_id, token_user_id, db)
    jasil_audit.stage(
        db,
        account_security_audit_actions.SESSION_REVOKE,
        target_type="session",
        target_id=session_id,
        target_owner_id=str(token_user_id),
        details=account_security_audit_actions.SessionsRevokedDetails(sessions_revoked=1),
    )
    db.commit()
    # The session id is the handle exchanged for tokens, so only a one-way fingerprint is logged.
    logger.info(
        "Deleted a user's session",
        extra=core_logger.context(user_id=token_user_id, session=core_hashing.log_fingerprint(session_id)),
    )


def delete_all_user_sessions(user_id: int, db: Session) -> int:
    """Stage the revocation of every session belonging to a user; the caller commits."""
    revoked = sessions_integration.delete_sessions_by_user(user_id, db)
    _stage_sessions_revoked(user_id, revoked, db)
    logger.info("Revoked a user's sessions", extra=core_logger.context(user_id=user_id, revoked=revoked))
    return revoked


def stage_delete_other_user_sessions(
    token_user_id: int,
    current_session_id: str,
    db: Session,
) -> int:
    """Stage the revocation of all of the user's sessions except their current one; the caller commits.

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
    revoked = sessions_integration.delete_sessions_by_user(
        token_user_id,
        db,
        exclude_session_id=current_session_id,
    )
    _stage_sessions_revoked(token_user_id, revoked, db)
    return revoked


def delete_other_user_sessions(
    token_user_id: int,
    current_session_id: str,
    db: Session,
) -> int:
    """Revoke all of the user's sessions except their current one and commit.

    Args:
        token_user_id: ID of the authenticated user.
        current_session_id: The caller's current session, preserved.
        db: SQLAlchemy session.

    Returns:
        Number of sessions revoked.
    """
    revoked = stage_delete_other_user_sessions(token_user_id, current_session_id, db)
    db.commit()
    logger.info(
        "User <token_user_id> ended <revoked> other session(s)",
        extra=core_logger.context(token_user_id=token_user_id, revoked=revoked),
    )
    return revoked


def _stage_password_written(
    action: jasil_audit.AuditAction,
    change: account_security_events.AccountSecurityChange,
    user_id: int,
    revoked: int,
    db: Session,
) -> None:
    """Stage the audit row and the event of a password that was just written.

    Args:
        action: The audit action naming who wrote the password.
        change: The change the event reports.
        user_id: ID of the user whose password changed.
        revoked: How many sessions the change ended.
        db: SQLAlchemy session.
    """
    jasil_audit.stage(
        db,
        action,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=account_security_audit_actions.SessionsRevokedDetails(sessions_revoked=revoked),
    )
    account_security_event_publishers.publish_account_security_changed(user_id, change, db)


def stage_change_own_password(
    user_id: int,
    current_password: str,
    new_password: str,
    mfa_code: str | None,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
    *,
    revoke_other_sessions: bool,
    current_session_id: str | None = None,
) -> None:
    """Stage a change of a user's own password after step-up verification; the caller commits.

    Args:
        user_id: ID of the authenticated user.
        current_password: Current password supplied for step-up.
        new_password: New plaintext password to store.
        mfa_code: Optional MFA code supplied for step-up.
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
        PermissionDeniedError: If the account has no local password; an administrator sets a first one.
        DomainError: If step-up verification or persistence fails.
        PasswordPolicyError: If the new password is too short, too common or matches the account's details.
    """
    # An account that signs in through an identity provider has no password to prove, so letting it set one
    # here would turn a stolen access token into a permanent password.
    if not credentials_integration.has_local_password(user_id, db):
        logger.warning(
            "Password change refused for user <user_id>: the account has no local password",
            extra=core_logger.context(user_id=user_id),
        )
        raise core_exceptions.PermissionDeniedError(
            "This account signs in through an identity provider and has no password to change"
        )
    step_up_service.verify_step_up_credentials(
        user_id,
        current_password,
        mfa_code,
        step_up_store,
        db,
    )

    server_settings = server_settings_integration.get_server_settings(db)
    db_user = users_integration.require_user(user_id, db)
    access_type = users_schema.normalize_access_type(db_user.access_type)
    hashed_password = credentials_integration.validate_and_hash_password_for_user(
        server_settings,
        access_type,
        new_password,
        db,
        username=db_user.username,
        email=db_user.email,
    )
    credentials_integration.set_local_password_hash(user_id, hashed_password, db)
    mfa_integration.clear_pending_mfa_for_user(user_id)

    revoked = 0
    if revoke_other_sessions:
        revoked = sessions_integration.delete_sessions_by_user(
            user_id,
            db,
            exclude_session_id=current_session_id,
        )
        logger.info(
            "User <user_id> revoked <revoked> other session(s) after password change",
            extra=core_logger.context(user_id=user_id, revoked=revoked),
        )

    _stage_password_written(
        account_security_audit_actions.PASSWORD_CHANGE,
        account_security_events.AccountSecurityChange.PASSWORD_CHANGED,
        user_id,
        revoked,
        db,
    )
    logger.info("User <user_id> changed password (step-up verified)", extra=core_logger.context(user_id=user_id))


def stage_password_reset_event(user_id: int, db: Session) -> None:
    """Stage the event of a password set through an emailed reset link; the caller commits.

    Args:
        user_id: ID of the user whose password was reset.
        db: SQLAlchemy session.
    """
    account_security_event_publishers.publish_account_security_changed(
        user_id, account_security_events.AccountSecurityChange.PASSWORD_RESET, db
    )


def change_managed_user_password(
    user_id: int,
    new_password: str,
    db: Session,
) -> None:
    """Stage a change of a managed user's password and the revocation of their auth state; the caller commits.

    Args:
        user_id: ID of the user whose password is changed.
        new_password: New plaintext password to store.
        db: SQLAlchemy session.

    Returns:
        None.

    Raises:
        PasswordPolicyError: If the new password is too short, too common or matches the account's details.
        DomainError: If password persistence fails.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    db_user = users_integration.require_user(user_id, db)
    access_type = users_schema.normalize_access_type(db_user.access_type)
    hashed_password = credentials_integration.validate_and_hash_password_for_user(
        server_settings,
        access_type,
        new_password,
        db,
        username=db_user.username,
        email=db_user.email,
    )
    credentials_integration.set_local_password_hash(user_id, hashed_password, db)
    revoked = sessions_integration.delete_sessions_by_user(user_id, db)
    mfa_integration.clear_pending_mfa_for_user(user_id)
    _stage_password_written(
        account_security_audit_actions.PASSWORD_SET,
        account_security_events.AccountSecurityChange.PASSWORD_SET_BY_ADMIN,
        user_id,
        revoked,
        db,
    )
    logger.info(
        "Changed a managed user's password and revoked sessions",
        extra=core_logger.context(user_id=user_id, revoked=revoked),
    )


def prepare_security_change_email(
    user_id: int,
    change: str,
    idp_id: int | None,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Return the notice of an account-security change for delivery after the database session closes.

    Args:
        user_id: The user whose account security changed.
        change: The kind of change, an ``AccountSecurityChange`` value or ``IDENTITY_PROVIDER_LINKED``.
        idp_id: The identity provider concerned by a link or unlink.
        frontend_host: Base URL of the frontend.
        db: Database session.

    Returns:
        The recipient, subject, HTML and text, or None when the user is missing or inactive.
    """
    user = users_integration.get_user(user_id, db)
    if user is None or not user.active:
        return None
    idp = identity_providers_integration.get_identity_provider(idp_id, db) if idp_id is not None else None
    locale = core_i18n.normalize_locale(user.preferred_language)
    return (
        user.email,
        *account_security_email_messages.get_account_security_changed_email(
            user.name, change, idp.name if idp is not None else None, frontend_host, locale
        ),
    )
