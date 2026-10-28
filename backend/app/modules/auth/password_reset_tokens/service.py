"""Password-reset token workflows and email preparation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.i18n as core_i18n
import modules.auth.computation as token_hashing
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


class PasswordPolicyError(core_exceptions.DomainError):
    """A replacement password failed policy validation."""

    status_code = 422
    code = "invalid-input"
    title = "Unprocessable Content"
    default_detail = "The password does not meet the configured policy"


def create_password_reset_token(user_id: int, db: Session) -> str:
    """Replace a user's reset tokens and commit the new token."""
    token, token_hash = token_hashing.generate_token_and_hash()
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
    return token


def request_password_reset_email(email: str, db: Session) -> None:
    """Stage and commit a reset-email request without revealing account existence."""
    if not server_settings_integration.is_mail_configured(db):
        raise core_exceptions.ServiceUnavailableError("Email service is not configured")
    user = users_integration.get_user_by_email(email, db)
    if user and user.active:
        password_reset_event_publishers.publish_password_reset_requested(user.id, db)
        db.commit()


def prepare_password_reset_email(
    user_id: int,
    frontend_host: str,
    db: Session,
) -> tuple[str, str, str, str] | None:
    """Create a durable reset link and return its email content for delivery after the session closes."""
    user = users_integration.get_user(user_id, db)
    if not user or not user.active:
        return None

    token = create_password_reset_token(user.id, db)
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
    try:
        hashed_password = credentials_integration.validate_and_hash_password_for_user(
            server_settings,
            users_schema.normalize_access_type(user.access_type),
            new_password,
            db,
        )
    except core_exceptions.InvalidInputError as err:
        raise PasswordPolicyError(err.detail) from err

    credentials_integration.set_local_password_hash(token_user_id, hashed_password, db)
    password_reset_crud.mark_user_password_reset_tokens_used(token_user_id, db)
    sessions_integration.delete_sessions_by_user(token_user_id, db)
    db.commit()
    mfa_integration.clear_pending_mfa_for_user(token_user_id)


def delete_expired_password_reset_tokens(db: Session) -> int:
    """Stage deletion of expired reset tokens."""
    return password_reset_crud.delete_expired_password_reset_tokens(db)
