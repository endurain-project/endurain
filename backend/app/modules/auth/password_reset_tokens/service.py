"""Password-reset token workflows and email preparation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jasil.providers import StateBackendUnavailableError, StateProvider
from sqlalchemy.orm import Session

import core.database as core_database
import core.email_cooldown as core_email_cooldown
import core.exceptions as core_exceptions
import core.i18n as core_i18n
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.computation as token_hashing
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.password_reset_tokens.crud as password_reset_crud
import modules.auth.password_reset_tokens.email_messages as password_reset_email_messages
import modules.auth.password_reset_tokens.event_publishers as password_reset_event_publishers
import modules.auth.password_reset_tokens.schema as password_reset_schema
import modules.auth.sessions.integration_service as sessions_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)

RESET_EMAIL_COOLDOWN_SECONDS = 300


def create_password_reset_token(user_id: int, event_id: str, db: Session) -> str:
    """Return the reset token for a reset-request event, minting and committing it on first use.

    The token is derived from the event id with the server secret, so redelivering the event yields the
    same token and leaves the link already mailed working; a later request is a new event and replaces it.

    Args:
        user_id: The user the token belongs to.
        event_id: The id of the ``auth.password_reset_requested`` event, stable across its retries.
        db: Database session.

    Returns:
        The raw token, which is not stored.
    """
    token = access_tokens_integration.hmac_sha256(f"password-reset:{event_id}")
    token_hash = token_hashing.sha256_hex(token)
    if password_reset_crud.password_reset_token_exists(token_hash, db):
        return token
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
    db.commit()
    logger.info("Password-reset token created", extra=core_logger.context(user_id=user_id))
    return token


def _may_reset_password(user: users_schema.UsersRead, db: Session) -> bool:
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


def request_password_reset_email(email: str, state: StateProvider, db: Session) -> None:
    """Stage and commit a reset-email request without revealing account existence.

    An account is mailed at most once per cooldown, so the endpoint cannot flood an inbox. A request inside
    the cooldown, or one the cooldown store cannot answer, sends nothing and still gets the same answer: the
    reply must not tell a registered address from an unregistered one. Nor is anything sent to an account that
    signs in through an identity provider and has no local password (a reset would give it one, so whoever
    controls its address would bypass the provider), or, while local sign-in is turned off, to an account that
    is not an administrator's.

    Args:
        email: The address the reset was requested for.
        state: The platform state provider, for the cooldown.
        db: Database session.

    Raises:
        ServiceUnavailableError: If mail is not configured.
    """
    if not server_settings_integration.is_mail_configured(db):
        raise core_exceptions.ServiceUnavailableError("Email service is not configured")
    user = users_integration.get_user_by_email(email, db)
    if not (user and user.active):
        return
    if not _may_reset_password(user, db):
        logger.warning(
            "Password-reset email not sent to user <user_id>: the account may not use a local password",
            extra=core_logger.context(user_id=user.id),
        )
        return
    try:
        if not core_email_cooldown.claim_email(state, "password_reset", user.id, RESET_EMAIL_COOLDOWN_SECONDS):
            return
    except StateBackendUnavailableError as err:
        logger.error("Password-reset cooldown unavailable", exc_info=err, extra=core_logger.context(user_id=user.id))
        return
    password_reset_event_publishers.publish_password_reset_requested(user.id, db)
    db.commit()
    logger.info("Password-reset email requested", extra=core_logger.context(user_id=user.id))


def prepare_password_reset_email(
    user_id: int,
    event_id: str,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Create a durable reset link and return its email content for delivery after the session closes.

    Args:
        user_id: The user who asked for the reset.
        event_id: The id of the request event; a retry of the event gets the same link.
        frontend_host: Base URL the link points at.
        db: Database session.

    Returns:
        The recipient, subject, HTML and text, or None when the user is missing or inactive.
    """
    user = users_integration.get_user(user_id, db)
    if not user or not user.active:
        return None

    token = create_password_reset_token(user.id, event_id, db)
    reset_link = f"{frontend_host}/reset-password?token={token}"
    locale = core_i18n.normalize_locale(user.preferred_language)
    subject, html_content, text_content = password_reset_email_messages.get_password_reset_email(
        user.name,
        reset_link,
        frontend_host,
        locale,
    )
    return user.email, subject, html_content, text_content


def use_password_reset_token(token: str, new_password: str, db: Session) -> None:
    """Consume a valid reset token and atomically change the password and revoke sessions."""
    token_user_id = password_reset_crud.claim_password_reset_token(token_hashing.sha256_hex(token), db)
    if token_user_id is None:
        raise core_exceptions.InvalidInputError("Invalid or expired password reset token")

    server_settings = server_settings_integration.get_server_settings(db)
    user = users_integration.require_user(token_user_id, db)
    if not _may_reset_password(user, db):
        logger.warning(
            "Password reset refused for user <user_id>: the account may not use a local password",
            extra=core_logger.context(user_id=token_user_id),
        )
        raise core_exceptions.InvalidInputError("Invalid or expired password reset token")
    try:
        hashed_password = credentials_integration.validate_and_hash_password_for_user(
            server_settings,
            users_schema.normalize_access_type(user.access_type),
            new_password,
            db,
        )
    except core_exceptions.InvalidInputError as err:
        raise credentials_contracts.PasswordPolicyError(err.detail) from err

    credentials_integration.set_local_password_hash(token_user_id, hashed_password, db)
    password_reset_crud.mark_user_password_reset_tokens_used(token_user_id, db)
    sessions_integration.delete_sessions_by_user(token_user_id, db)
    db.commit()
    mfa_integration.clear_pending_mfa_for_user(token_user_id)
    logger.info("Password reset completed", extra=core_logger.context(user_id=token_user_id))


def delete_expired_password_reset_tokens(db: Session) -> int:
    """Delete expired reset tokens, one batch per commit."""
    now = datetime.now(UTC)
    return core_database.delete_in_batches(
        lambda limit: password_reset_crud.delete_expired_password_reset_tokens(now, limit, db), db
    )
