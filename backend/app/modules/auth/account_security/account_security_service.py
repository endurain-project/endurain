"""Auth-owned account security workflows."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, NoReturn
from zoneinfo import ZoneInfo

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.i18n as core_i18n
import core.logger as core_logger
import core.pagination as core_pagination
import core.timezone as core_timezone
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.email_messages as account_security_email_messages
import modules.auth.account_security.event_publishers as account_security_event_publishers
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.authentication.integration_service as authentication_integration
import modules.auth.authentication.schema as authentication_schema
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.integration_service as identity_providers_integration
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.login_audit.integration_service as login_audit_integration
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.password_reset_tokens.integration_service as password_reset_tokens_integration
import modules.auth.sessions.audit_actions as sessions_audit_actions
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
        sessions_audit_actions.SESSION_REVOKE,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=sessions_audit_actions.SessionsRevokedDetails(sessions_revoked=revoked),
    )


def list_user_sessions(
    token_user_id: int,
    page: core_pagination.PageParams,
    db: Session,
) -> auth_sessions_schema.UserSessionsPage:
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
        sessions_audit_actions.SESSION_REVOKE,
        target_type="session",
        target_id=session_id,
        target_owner_id=str(token_user_id),
        details=sessions_audit_actions.SessionsRevokedDetails(sessions_revoked=1),
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


def end_other_sessions(user_id: int, current_session_id: str | None, db: Session) -> int:
    """Stage the end of the user's sessions except the caller's, after a change of an authentication factor.

    The caller stages the audit row that reports the count, in the transaction that commits the change.

    Args:
        user_id: ID of the user whose other sessions end.
        current_session_id: The caller's session, kept so the caller stays signed in.
        db: SQLAlchemy session.

    Returns:
        Number of sessions ended.
    """
    revoked = sessions_integration.delete_sessions_by_user(user_id, db, exclude_session_id=current_session_id)
    logger.info(
        "User <user_id> revoked <revoked> other session(s) after a change of an authentication factor",
        extra=core_logger.context(user_id=user_id, revoked=revoked),
    )
    return revoked


def _stage_credential_changed(
    action: jasil_audit.AuditAction,
    change: account_security_events.AccountSecurityChange,
    user_id: int,
    revoked: int,
    db: Session,
) -> None:
    """Stage the audit row and the event of a credential change that ended the user's sessions.

    Args:
        action: The audit action naming the change.
        change: The change the event reports.
        user_id: ID of the user whose credential changed.
        revoked: How many sessions the change ended.
        db: SQLAlchemy session.
    """
    jasil_audit.stage(
        db,
        action,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=sessions_audit_actions.SessionsRevokedDetails(sessions_revoked=revoked),
    )
    account_security_event_publishers.publish_account_security_changed(user_id, change, db)


def _stage_own_password(user_id: int, new_password: str, db: Session) -> users_schema.UserRead:
    """Stage the owner's new password, which clears any requirement to change it, and void the unused reset tokens.

    Args:
        user_id: ID of the user whose password changes.
        new_password: New plaintext password to store.
        db: SQLAlchemy session.

    Returns:
        The user whose password changed.

    Raises:
        PasswordPolicyError: If the new password is the current one, blank, too short, too common or matches the
            account's details.
    """
    credentials_integration.ensure_password_differs_from_current(user_id, new_password, db)
    server_settings = server_settings_integration.get_server_settings(db)
    db_user = users_integration.require_user(user_id, db)
    hashed_password = credentials_integration.validate_and_hash_password_for_user(
        server_settings,
        users_schema.normalize_access_type(db_user.access_type),
        new_password,
        db,
        username=db_user.username,
        email=db_user.email,
    )
    credentials_integration.set_local_password_hash(user_id, hashed_password, db, change_required=False)
    password_reset_tokens_integration.revoke_unused_tokens(user_id, db)
    return db_user


def stage_required_password_change(user_id: int, new_password: str, db: Session) -> None:
    """Stage the new password an administrator-set password makes its owner choose at sign-in; the caller commits.

    The password policy is checked before anything is staged. The change is audited and published like any other
    change of an own password. No session exists to end: the owner has not signed in yet.

    Args:
        user_id: ID of the user who chose the password.
        new_password: New plaintext password to store.
        db: SQLAlchemy session.

    Raises:
        PasswordPolicyError: If the new password is the current one, blank, too short, too common or matches the
            account's details.
    """
    _stage_own_password(user_id, new_password, db)
    _stage_credential_changed(
        account_security_audit_actions.PASSWORD_CHANGE,
        account_security_events.AccountSecurityChange.PASSWORD_CHANGED,
        user_id,
        0,
        db,
    )
    logger.info("User <user_id> replaced an administrator-set password", extra=core_logger.context(user_id=user_id))


def stage_change_own_password(
    user_id: int,
    current_password: str | None,
    new_password: str,
    mfa_code: str | None,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
    *,
    revoke_other_sessions: bool,
    current_session_id: str,
) -> None:
    """Stage a change of a user's own password after step-up verification; the caller commits.

    The user's unused password-reset tokens are voided with the change.

    Args:
        user_id: ID of the authenticated user.
        current_password: Current password supplied for step-up, or None when the request carried none.
        new_password: New plaintext password to store.
        mfa_code: Optional MFA code supplied for step-up.
        step_up_store: Step-up lockout store.
        db: SQLAlchemy session.
        revoke_other_sessions: When True, delete all of the user's
            other sessions (keeping ``current_session_id``) so a
            password change can evict a suspected attacker.
        current_session_id: Session ID of the caller, which owns the step-up lockout counter and is preserved
            when ``revoke_other_sessions`` is True so the caller is not logged out.

    Returns:
        None.

    Raises:
        PermissionDeniedError: If the account has no local password; an administrator sets a first one.
        DomainError: If step-up verification or persistence fails.
        PasswordPolicyError: If the new password is the current one, blank, too short, too common or matches the
            account's details.
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
        session_id=current_session_id,
    )

    db_user = _stage_own_password(user_id, new_password, db)
    mfa_integration.clear_pending_mfa_for_user(user_id)
    authentication_integration.clear_account_login_lockout(db_user.username)

    revoked = 0
    if revoke_other_sessions:
        revoked = end_other_sessions(user_id, current_session_id, db)

    _stage_credential_changed(
        account_security_audit_actions.PASSWORD_CHANGE,
        account_security_events.AccountSecurityChange.PASSWORD_CHANGED,
        user_id,
        revoked,
        db,
    )
    logger.info("User <user_id> changed password (step-up verified)", extra=core_logger.context(user_id=user_id))


def change_managed_user_password(
    user_id: int,
    new_password: str,
    db: Session,
) -> None:
    """Stage a change of a managed user's password and the revocation of their auth state; the caller commits.

    The user's sessions and unused password-reset tokens are revoked with the change, and the user must choose a new
    password at the next sign-in.

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
    # The administrator knows this password, so its owner must choose a new one at the next sign-in.
    credentials_integration.set_local_password_hash(user_id, hashed_password, db, change_required=True)
    password_reset_tokens_integration.revoke_unused_tokens(user_id, db)
    revoked = sessions_integration.delete_sessions_by_user(user_id, db)
    mfa_integration.clear_pending_mfa_for_user(user_id)
    authentication_integration.clear_account_login_lockout(db_user.username)
    _stage_credential_changed(
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


def reset_managed_user_mfa(user_id: int, db: Session) -> None:
    """Stage a reset of a managed user's MFA and the end of all of their sessions; the caller commits.

    Args:
        user_id: ID of the user whose MFA is reset.
        db: SQLAlchemy session.

    Raises:
        NotFoundError: If the user does not exist.
        InvalidInputError: If MFA is not enabled for the user.
    """
    mfa_integration.disable_user_mfa(user_id, db)
    revoked = sessions_integration.delete_sessions_by_user(user_id, db)
    mfa_integration.clear_pending_mfa_for_user(user_id)
    _stage_credential_changed(
        account_security_audit_actions.MFA_RESET,
        account_security_events.AccountSecurityChange.MFA_RESET_BY_ADMIN,
        user_id,
        revoked,
        db,
    )
    logger.info(
        "Reset a managed user's MFA and revoked sessions",
        extra=core_logger.context(user_id=user_id, revoked=revoked),
    )


def require_managed_user_password_change(user_id: int, db: Session) -> None:
    """Stage the requirement that a managed user choose a new password at the next sign-in; the caller commits.

    The current password stays valid until then. The user's sessions end and a pending MFA sign-in is dropped, so the
    requirement applies at the next sign-in.

    Args:
        user_id: ID of the user who must replace their password.
        db: SQLAlchemy session.

    Raises:
        NotFoundError: If the user does not exist.
        ConflictError: If the user has no local password.
    """
    users_integration.require_user(user_id, db)
    credentials_integration.require_password_change(user_id, db)
    revoked = sessions_integration.delete_sessions_by_user(user_id, db)
    mfa_integration.clear_pending_mfa_for_user(user_id)
    _stage_credential_changed(
        account_security_audit_actions.PASSWORD_CHANGE_REQUIRE,
        account_security_events.AccountSecurityChange.PASSWORD_CHANGE_REQUIRED_BY_ADMIN,
        user_id,
        revoked,
        db,
    )
    logger.info(
        "Required a managed user to change their password and revoked sessions",
        extra=core_logger.context(user_id=user_id, revoked=revoked),
    )


def _refuse_password_change(
    reason: login_audit_actions.LoginFailureReason, pending: authentication_integration.PendingPasswordChange | None
) -> NoReturn:
    """Audit and log a refused password-change step, then answer with the one message every cause shares.

    Args:
        reason: Why the step was refused.
        pending: The pending password change the challenge named, or None when it named none.

    Raises:
        UnauthenticatedError: Always.
    """
    logger.warning("Password change refused: <reason>", extra=core_logger.context(reason=reason.value))
    login_audit_integration.record_login_refusal(
        login_audit_actions.LoginMethod.PASSWORD,
        jasil_audit.Outcome.FAILURE,
        reason,
        mfa=pending.mfa if pending else False,
        user_id=pending.user_id if pending else None,
    )
    raise core_exceptions.UnauthenticatedError("Unable to authenticate with provided credentials", scheme="Bearer")


def complete_password_change(
    ip_address: str,
    user_agent: str,
    change_request: authentication_schema.PasswordChangeLoginRequest,
    client_type: auth_constants.ClientType,
    password_change_store: authentication_integration.PendingPasswordChangeStore,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    *,
    device_id: str | None,
) -> authentication_schema.AuthOutcome[authentication_schema.FinishedLoginRead]:
    """Replace an administrator-set password and finish the sign-in that asked for it.

    The pending change is looked up first and claimed only after the new password passed the account's policy, so a
    rejected password leaves the challenge usable. The new password, its audit row and event, and the session are one
    transaction. The sign-in then continues as the verified sign-in that started the change did: the recorded client
    type, PKCE values and MFA outcome decide the answer.

    Args:
        ip_address: Client address, recorded on the session.
        user_agent: Client user agent, recorded on the session.
        change_request: The challenge the sign-in returned and the new password.
        client_type: The type of client making the request; it must be the one that signed in.
        password_change_store: Store for pending password changes.
        password_hasher: Hasher for the stored refresh token, and the dummy verify of an unknown challenge.
        token_manager: Token manager that signs the tokens.
        db: Database session.
        device_id: Device id from the browser's device cookie or the mobile app's ``X-Device-Id`` header, or None
            when the client sent no valid one.

    Returns:
        The outcome of the finished sign-in: the tokens or, for a mobile PKCE client, the session to exchange.

    Raises:
        UnauthenticatedError: If the challenge is unknown, expired, claimed, from another client type, or no longer
            needed because the password was changed meanwhile (answered alike).
        PermissionDeniedError: If the account is no longer active.
        PasswordPolicyError: If the new password is the current one, blank, too short, too common or matches the
            account's details.
        ServiceUnavailableError: If the shared state is unavailable.
    """
    challenge = change_request.password_change_challenge
    invalid = login_audit_actions.LoginFailureReason.PASSWORD_CHANGE_CHALLENGE_INVALID
    try:
        pending = password_change_store.get(challenge)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        authentication_integration.raise_auth_security_store_unavailable(err)
    if pending is None or pending.client_type != client_type:
        # Run a dummy Argon2 verify so the wall-clock latency of the unknown-challenge branch matches the branches
        # that do real work.
        password_hasher.dummy_verify()
        _refuse_password_change(invalid, None)

    user = users_integration.get_user(pending.user_id, db)
    if user is None:
        _refuse_password_change(invalid, pending)
    users_integration.require_active_user(user)
    if not credentials_integration.is_password_change_required(user.id, db):
        _refuse_password_change(invalid, pending)

    # The user has no principal yet, so the context names them. A password that fails the policy raises before
    # anything is staged and leaves the challenge unclaimed.
    with jasil_audit.audit_context(
        actor_type=jasil_audit.ActorType.USER, actor_id=str(user.id), credential_type="password"
    ):
        stage_required_password_change(user.id, change_request.password, db)

    try:
        claimed = password_change_store.claim(challenge)
    except lockout_contracts.AuthSecurityStoreUnavailableError as err:
        db.rollback()
        authentication_integration.raise_auth_security_store_unavailable(err)
    if claimed != pending:
        db.rollback()
        _refuse_password_change(login_audit_actions.LoginFailureReason.PASSWORD_CHANGE_CHALLENGE_CLAIMED, pending)

    return authentication_integration.finish_login(
        ip_address,
        user_agent,
        user,
        client_type,
        pending.code_challenge,
        pending.code_challenge_method,
        password_hasher,
        token_manager,
        db,
        mfa=pending.mfa,
        device_id=device_id,
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


def prepare_new_device_sign_in_email(
    user_id: int,
    browser: str,
    operating_system: str,
    ip_address: str,
    method: str,
    signed_in_at: datetime,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Return the notice of a sign-in from a new device for delivery after the database session closes.

    The time is given in the user's timezone, or the server's when the user has none.

    Args:
        user_id: The user who signed in.
        browser: The browser family the sign-in's user agent names.
        operating_system: The operating-system family the sign-in's user agent names.
        ip_address: The client address of the sign-in.
        method: How the user signed in, a ``SignInMethod`` value.
        signed_in_at: When the sign-in happened.
        frontend_host: Base URL of the frontend.
        db: Database session.

    Returns:
        The recipient, subject, HTML and text, or None when the user is missing or inactive.
    """
    user = users_integration.get_user(user_id, db)
    if user is None or not user.active:
        return None
    local_time = signed_in_at.astimezone(ZoneInfo(core_timezone.or_default(user.timezone)))
    return (
        user.email,
        *account_security_email_messages.get_new_device_sign_in_email(
            user.name,
            browser,
            operating_system,
            ip_address,
            method,
            local_time,
            frontend_host,
            core_i18n.normalize_locale(user.preferred_language),
        ),
    )
