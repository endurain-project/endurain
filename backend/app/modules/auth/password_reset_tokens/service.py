"""Password-reset request, token and email workflows."""

import uuid
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jasil.audit as jasil_audit
from jasil.providers import StateBackendUnavailableError, StateProvider
from sqlalchemy.orm import Session

import core.database as core_database
import core.email_cooldown as core_email_cooldown
import core.exceptions as core_exceptions
import core.i18n as core_i18n
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.api_keys.integration_service as api_keys_integration
import modules.auth.authentication.integration_service as authentication_integration
import modules.auth.computation as token_hashing
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.lockout.integration_service as lockout_integration
import modules.auth.password_reset_tokens.audit_actions as password_reset_audit_actions
import modules.auth.password_reset_tokens.crud as password_reset_crud
import modules.auth.password_reset_tokens.email_messages as password_reset_email_messages
import modules.auth.password_reset_tokens.event_publishers as password_reset_event_publishers
import modules.auth.password_reset_tokens.events as password_reset_events
import modules.auth.password_reset_tokens.schema as password_reset_schema
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)

RESET_EMAIL_COOLDOWN_SECONDS = 300
UNUSABLE_RESET_MESSAGE = "Invalid or expired password reset token"


def _stage_password_reset_token(user_id: uuid.UUID, token_hash: str, db: Session) -> None:
    """Stage a new reset token for a user, replacing their unused ones; the caller commits.

    Args:
        user_id: The user the token belongs to.
        token_hash: The hash of the raw token, which is not stored.
        db: Database session.
    """
    now = datetime.now(UTC)
    reset_token = password_reset_schema.PasswordResetToken(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=token_hash,
        created_at=now,
        expires_at=now + timedelta(hours=1),
        used=False,
    )
    password_reset_crud.mark_user_password_reset_tokens_used(user_id, db)
    password_reset_crud.create_password_reset_token(reset_token, db)


def _may_reset_password(user: users_schema.UserRead, db: Session) -> bool:
    """Tell whether an account may set its password through a reset link.

    Args:
        user: The account.
        db: Database session.

    Returns:
        True when the account has a local password and may sign in with it under the server's settings.
    """
    return credentials_integration.has_local_password(user.id, db) and credentials_integration.allows_password_sign_in(
        server_settings_integration.get_server_settings(db), users_schema.normalize_access_type(user.access_type)
    )


def _can_reset_password(user: users_schema.UserRead, db: Session) -> bool:
    """Tell whether an active account may set its password through a reset link."""
    return user.active and _may_reset_password(user, db)


def _record_reset_request_denied(user_id: uuid.UUID) -> None:
    """Record a reset request for an account that may not reset its password; the requester gets no signal.

    Args:
        user_id: The account the request named.
    """
    jasil_audit.record_detached(
        password_reset_audit_actions.PASSWORD_RESET_REQUEST,
        outcome=jasil_audit.Outcome.DENIED,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
    )


def _claim_reset_cooldown(user_id: uuid.UUID, event_id: str, state: StateProvider) -> bool:
    """Claim the account's reset-email cooldown for an event; False when another went out recently or the store is unreachable."""
    try:
        return core_email_cooldown.claim_email(
            state, "password_reset", user_id, RESET_EMAIL_COOLDOWN_SECONDS, claimant=event_id
        )
    except StateBackendUnavailableError as err:
        logger.error("Password-reset cooldown unavailable", exc_info=err, extra=core_logger.context(user_id=user_id))
        return False


def request_password_reset_email(email: str, ip_address: str, user_agent: str, db: Session) -> None:
    """Stage and commit a reset request for an address, doing the same work whether or not an account has it.

    The request looks the address up once and stages one event naming the account, or nobody. Everything that
    depends on the account (its state, the cooldown, the audit row) happens in the event's subscriber, so the
    answer and its timing do not tell a registered address from an unregistered one.

    Args:
        email: The address the reset was requested for.
        ip_address: The requester's client address, which the subscriber records on its audit rows.
        user_agent: The requester's ``User-Agent``, for the same rows.
        db: Database session.

    Raises:
        ServiceUnavailableError: If mail is not configured.
    """
    if not server_settings_integration.is_mail_configured(db):
        raise core_exceptions.ServiceUnavailableError("Email service is not configured")
    user = users_integration.get_user_by_email(email, db)
    password_reset_event_publishers.publish_password_reset_requested(
        None if user is None else user.id, ip_address, user_agent, db
    )
    db.commit()
    logger.debug("Password-reset request queued")


def prepare_password_reset_email(
    payload: password_reset_events.PasswordResetRequestedPayload,
    event_id: str,
    frontend_host: str,
    state: StateProvider,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Decide on a reset request and return the email to send, for delivery after the session closes.

    An account is mailed at most once per cooldown, so the endpoint cannot flood an inbox. Nothing is sent to
    an unknown address, an inactive account, or an account that may not use a local password (a reset would
    give an identity-provider account one, so whoever controls its address would bypass the provider; while
    local sign-in is off only administrators keep it). Each refusal and each admitted request is audited with
    the requester's client data.

    The reset token derives from the event id and the cooldown claim is held by the event, so a redelivery of an
    admitted event finds its token, skips the cooldown and the audit row, and returns the same link. A retry
    after a failed commit finds no token but its own claim, and stages the token and row again. A later request
    is a new event and replaces it.

    Args:
        payload: The request event's payload.
        event_id: The id of the request event, stable across its retries.
        frontend_host: Base URL the link points at.
        state: The platform state provider, for the cooldown.
        db: Database session.

    Returns:
        The recipient, subject, HTML and text, or None when nothing is to be sent.
    """
    with jasil_audit.audit_context(ip_address=payload.ip_address, user_agent=payload.user_agent):
        if payload.user_id is None:
            jasil_audit.record_detached(
                password_reset_audit_actions.PASSWORD_RESET_REQUEST, outcome=jasil_audit.Outcome.FAILURE
            )
            return None
        user = users_integration.get_user(payload.user_id, db)
        if user is None:
            logger.debug("Password-reset request skipped: the user no longer exists")
            return None
        if not user.active:
            _record_reset_request_denied(user.id)
            return None
        if not _may_reset_password(user, db):
            _record_reset_request_denied(user.id)
            logger.warning(
                "Password-reset email not sent to user <user_id>: the account may not use a local password",
                extra=core_logger.context(user_id=user.id),
            )
            return None
        token = access_tokens_integration.derive_email_token(f"password-reset:{event_id}")
        token_hash = token_hashing.sha256_hex(token)
        if not password_reset_crud.password_reset_token_exists(token_hash, db):
            if not _claim_reset_cooldown(user.id, event_id, state):
                return None
            _stage_password_reset_token(user.id, token_hash, db)
            jasil_audit.stage(
                db,
                password_reset_audit_actions.PASSWORD_RESET_REQUEST,
                target_type="user",
                target_id=str(user.id),
                target_owner_id=str(user.id),
            )
            db.commit()
            logger.info("Password-reset email requested", extra=core_logger.context(user_id=user.id))
    reset_link = f"{frontend_host}/reset-password?token={token}"
    locale = core_i18n.normalize_locale(user.preferred_language)
    subject, html_content, text_content = password_reset_email_messages.get_password_reset_email(
        user.name,
        reset_link,
        frontend_host,
        locale,
    )
    return user.email, subject, html_content, text_content


def validate_password_reset_token(token: str, db: Session) -> None:
    """Check that confirm would accept a reset token, without consuming it or recording anything.

    Unknown, used and expired tokens, and tokens of an account that may not reset its password, fail
    identically, so the answer reveals nothing about the token or its owner.

    Args:
        token: The raw reset token.
        db: Database session.

    Raises:
        InvalidInputError: If the token is unknown, used or expired, or the account is inactive or may not
            reset its password.
    """
    token_user_id = password_reset_crud.get_usable_password_reset_token_user_id(token_hashing.sha256_hex(token), db)
    if token_user_id is None or not _can_reset_password(users_integration.require_user(token_user_id, db), db):
        raise core_exceptions.InvalidInputError(UNUSABLE_RESET_MESSAGE)


def use_password_reset_token(token: str, new_password: str, db: Session) -> None:
    """Consume a valid reset token and atomically change the password and revoke sessions.

    Args:
        token: The raw reset token.
        new_password: The password chosen.
        db: Database session.

    Raises:
        InvalidInputError: If the token is invalid or expired, or the account is inactive or may not reset its password.
        PasswordPolicyError: If the password is the current one, blank, too short, too common, breached or matches
            the account's details.
    """
    server_settings = server_settings_integration.get_server_settings(db)
    # The breach check is a network call, so it runs before the claim opens the write transaction.
    credentials_integration.reject_breached_password(server_settings, new_password, db)
    token_hash = token_hashing.sha256_hex(token)
    token_user_id = password_reset_crud.get_usable_password_reset_token_user_id(token_hash, db)
    if token_user_id is not None:
        # The generation row is the first lock taken; the claim below writes the token row.
        security_generation_integration.stage_bump(token_user_id, db)
        token_user_id = password_reset_crud.claim_password_reset_token(token_hash, db)
    if token_user_id is None:
        jasil_audit.record_detached(password_reset_audit_actions.PASSWORD_RESET, outcome=jasil_audit.Outcome.FAILURE)
        raise core_exceptions.InvalidInputError(UNUSABLE_RESET_MESSAGE)

    user = users_integration.require_user(token_user_id, db)
    if not _can_reset_password(user, db):
        logger.warning(
            "Password reset refused for user <user_id>: the account is inactive or may not use a local password",
            extra=core_logger.context(user_id=token_user_id),
        )
        jasil_audit.record_detached(
            password_reset_audit_actions.PASSWORD_RESET,
            outcome=jasil_audit.Outcome.DENIED,
            target_type="user",
            target_id=str(token_user_id),
            target_owner_id=str(token_user_id),
        )
        raise core_exceptions.InvalidInputError(UNUSABLE_RESET_MESSAGE)
    credentials_integration.ensure_password_differs_from_current(token_user_id, new_password, db)
    hashed_password = credentials_integration.validate_and_hash_password_for_user(
        server_settings,
        users_schema.normalize_access_type(user.access_type),
        new_password,
        db,
        username=user.username,
        email=user.email,
    )

    credentials_integration.set_local_password_hash(token_user_id, hashed_password, db, change_required=False)
    password_reset_crud.mark_user_password_reset_tokens_used(token_user_id, db)
    sessions_integration.delete_sessions_by_user(token_user_id, db)
    # Whoever held the old password may hold a key, and the owner has just proved they hold the mailbox.
    api_keys_integration.revoke_user_api_keys(token_user_id, db)
    jasil_audit.stage(
        db,
        password_reset_audit_actions.PASSWORD_RESET,
        target_type="user",
        target_id=str(token_user_id),
        target_owner_id=str(token_user_id),
    )
    password_reset_event_publishers.publish_password_reset_completed(token_user_id, db)
    db.commit()
    authentication_integration.clear_account_login_lockout(token_user_id)
    lockout_integration.clear_step_up_account_lockout(token_user_id)
    logger.info("Password reset completed", extra=core_logger.context(user_id=token_user_id))


def delete_expired_password_reset_tokens(db: Session) -> int:
    """Delete expired reset tokens, one batch per commit."""
    now = datetime.now(UTC)
    return core_database.delete_in_batches(
        lambda limit: password_reset_crud.delete_expired_password_reset_tokens(now, limit, db), db
    )
