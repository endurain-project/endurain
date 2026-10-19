"""Utility functions for password reset token operations."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jasil.providers as platform_providers
from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.config as core_config
import core.i18n as core_i18n
import core.logger as core_logger
import core.mail as core_mail
import modules.auth._internal.security_stores as auth_security_stores
import modules.auth.credentials.crud as auth_credentials_crud
import modules.auth.password_policy as auth_password_policy
import modules.auth.password_reset_tokens.crud as password_reset_tokens_crud
import modules.auth.password_reset_tokens.event_publishers as password_reset_tokens_event_publishers
import modules.auth.password_reset_tokens.schema as password_reset_tokens_schema
import modules.auth.sessions.crud as auth_sessions_crud
import modules.auth.token_hashing as token_hashing
import modules.server_settings.utils as server_settings_utils
import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema
import modules.users.users.utils as users_utils
from core.database import SessionLocal
from modules.auth.identity_service import IdentityService
from modules.auth.password_reset_tokens import (
    email_messages as password_reset_tokens_email_messages,
)

logger = core_logger.get_logger(__name__)


def create_password_reset_token(user_id: int, db: Session) -> str:
    """
    Create and persist a password reset token for a user.

    Earlier unused tokens of the user are invalidated in the same commit, so only the
    newest reset link works.

    Args:
        user_id: ID of the user requesting the reset.
        db: Active SQLAlchemy session.

    Returns:
        The plaintext token to deliver to the user.
        Only the token hash is stored in the database.
    """
    # Generate token and hash
    token, token_hash = token_hashing.generate_token_and_hash()

    # Create token object
    reset_token = password_reset_tokens_schema.PasswordResetToken(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=token_hash,
        created_at=datetime.now(UTC),
        expires_at=(datetime.now(UTC) + timedelta(hours=1)),
        used=False,
    )

    # Invalidate earlier tokens, then save the new one (the create commits both)
    password_reset_tokens_crud.mark_user_password_reset_tokens_used(user_id, db)
    password_reset_tokens_crud.create_password_reset_token(reset_token, db)

    # Return the plain token (not the hash)
    return token


def request_password_reset_email(email: str, db: Session) -> None:
    """
    Queue a password reset email for the given address.

    Unknown and inactive accounts are silently ignored so the response never reveals
    whether an email exists.

    Args:
        email: Recipient email address.
        db: Active SQLAlchemy session.

    Returns:
        None

    Raises:
        HTTPException: 503 if the email service is not configured.
    """
    # Check if email service is configured
    if not core_mail.is_mail_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        )

    # Find user by email
    user = users_crud.get_user_by_email(email, db)
    if not user or not user.active:
        # Don't reveal if the email exists or the user is inactive
        return

    password_reset_tokens_event_publishers.publish_password_reset_requested(user.id, db)


def send_password_reset_email_to_user(user_id: int, mail: platform_providers.MailProvider, db: Session) -> bool:
    """
    Create a reset token and email the reset link to a user.

    The token is committed before sending, so the link in the email always works.

    Args:
        user_id: ID of the user to email.
        mail: The platform mail provider.
        db: Active SQLAlchemy session.

    Returns:
        True if the email was handed to the mail server, False if it was skipped.

    Raises:
        MailError: On a transient delivery failure.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user or not user.active:
        logger.debug(
            "Skipped password reset email: user missing or inactive", extra=core_logger.context(user_id=user_id)
        )
        return False

    token = create_password_reset_token(user.id, db)
    reset_link = f"{core_config.settings.ENDURAIN_HOST}/reset-password?token={token}"

    # Build localized email using the user's preferred language
    locale = core_i18n.normalize_locale(user.preferred_language)
    subject, html_content, text_content = password_reset_tokens_email_messages.get_password_reset_email(
        user.name, reset_link, core_config.settings.ENDURAIN_HOST, locale
    )
    return core_mail.send_email(mail, user.email, subject, html_content, text_content)


def use_password_reset_token(
    token: str,
    new_password: str,
    identity_service: IdentityService,
    db: Session,
) -> None:
    """
    Reset a user's password using a valid reset token.

    Args:
        token: Plaintext reset token from the email link.
        new_password: New plaintext password to set.
        identity_service: Identity service dependency.
        db: Active SQLAlchemy session.

    Returns:
        None

    Raises:
        HTTPException: 400 if the token is invalid or expired.
        HTTPException: 422 if the new password fails the account's password policy.
        HTTPException: 500 if password update or token marking fails.
    """
    # Hash the provided token to find the database record
    token_hash = token_hashing.sha256_hex(token)

    token_user_id = password_reset_tokens_crud.claim_password_reset_token(token_hash, db)
    if token_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token",
        )

    server_settings = server_settings_utils.get_server_settings_or_404(db)
    db_user = users_utils.get_user_by_id_or_404(token_user_id, db)
    access_type = users_schema.normalize_access_type(db_user.access_type)
    try:
        hashed_password = auth_password_policy.validate_and_hash_for_user(
            identity_service,
            server_settings,
            access_type,
            new_password,
        )
    except HTTPException as err:
        # Re-raised as 422 (distinct from the 400 above) so callers can tell a
        # weak new password apart from an invalid/expired token instead of
        # conflating both under the same status code.
        if err.status_code == status.HTTP_400_BAD_REQUEST:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=err.detail,
            ) from err
        raise

    try:
        auth_credentials_crud.upsert_password_hash(
            token_user_id,
            hashed_password,
            db,
            commit=False,
        )
        password_reset_tokens_crud.mark_user_password_reset_tokens_used(token_user_id, db)
        auth_sessions_crud.delete_sessions_by_user(token_user_id, db, commit=False)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset password",
        ) from err

    # Drop any in-flight pending-MFA login that was started with the
    # now-rotated password.
    auth_security_stores.clear_pending_mfa_for_user(token_user_id)


def delete_invalid_tokens_from_db() -> None:
    """
    Remove expired password reset tokens from the database.

    Opens a new session, deletes expired tokens, and logs the count if any were
        removed.

    Returns:
        None
    """
    # Create a new database session using context manager
    with SessionLocal() as db:
        # Get num tokens deleted
        num_deleted = password_reset_tokens_crud.delete_expired_password_reset_tokens(db)

        # Log the number of deleted tokens
        if num_deleted > 0:
            logger.info(f"Deleted {num_deleted} expired password reset tokens", extra=core_logger.context(console=True))
