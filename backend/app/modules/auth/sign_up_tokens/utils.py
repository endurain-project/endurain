"""Utility functions for sign-up token operations."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jasil.providers as platform_providers
from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

import core.config as core_config
import core.i18n as core_i18n
import core.logger as core_logger
import core.mail as core_mail
import modules.auth.sign_up_tokens.crud as sign_up_tokens_crud
import modules.auth.sign_up_tokens.email_messages as sign_up_tokens_email_messages
import modules.auth.sign_up_tokens.event_publishers as sign_up_tokens_event_publishers
import modules.auth.sign_up_tokens.schema as sign_up_tokens_schema
import modules.auth.token_hashing as token_hashing
import modules.users.users.crud as users_crud
import modules.users.users.utils as users_utils
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


def create_sign_up_token(user_id: int, db: Session) -> str:
    """
    Create and persist a sign-up token for a user.

    Earlier unused tokens of the user are invalidated in the same commit, so only the
    newest verification link works.

    Args:
        user_id: ID of the user signing up.
        db: Active SQLAlchemy session.

    Returns:
        The plaintext token to deliver to the user.
        Only the hash is stored in the database.
    """
    # Generate token and hash
    token, token_hash = token_hashing.generate_token_and_hash()

    # Create token object
    reset_token = sign_up_tokens_schema.SignUpToken(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=token_hash,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=24),  # 24 hour expiration
        used=False,
    )

    # Invalidate earlier tokens, then save the new one (the create commits both)
    sign_up_tokens_crud.mark_user_sign_up_tokens_used(user_id, db)
    sign_up_tokens_crud.create_sign_up_token(reset_token, db)

    # Return the plain token (not the hash)
    return token


def _require_mail_configured() -> None:
    """Raise 503 when outgoing email is not configured."""
    if not core_mail.is_mail_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        )


def request_sign_up_verification_email(user_id: int, db: Session) -> None:
    """
    Queue the sign-up verification email for a user.

    Args:
        user_id: ID of the user who signed up.
        db: Active SQLAlchemy session.

    Raises:
        HTTPException: 503 if the email service is not configured.
    """
    _require_mail_configured()
    sign_up_tokens_event_publishers.publish_sign_up_verification_requested(user_id, db)


def request_sign_up_admin_approval_emails(user_id: int, db: Session) -> None:
    """
    Queue one approval request email per admin for a new sign-up.

    Args:
        user_id: ID of the user who signed up.
        db: Active SQLAlchemy session.

    Raises:
        HTTPException: 503 if the email service is not configured.
    """
    _require_mail_configured()
    for admin in users_utils.get_admin_users_or_404(db):
        sign_up_tokens_event_publishers.publish_sign_up_approval_requested(user_id, admin.id, db)


def request_sign_up_approved_email(user_id: int, db: Session) -> None:
    """
    Queue the approval notice email for a user.

    Args:
        user_id: ID of the approved user.
        db: Active SQLAlchemy session.

    Raises:
        HTTPException: 503 if the email service is not configured.
    """
    _require_mail_configured()
    sign_up_tokens_event_publishers.publish_sign_up_approved(user_id, db)


def send_sign_up_verification_email_to_user(user_id: int, mail: platform_providers.MailProvider, db: Session) -> bool:
    """
    Create a verification token and email the link to a user.

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
    if not user:
        logger.debug("Skipped sign-up verification email: user missing", extra=core_logger.context(user_id=user_id))
        return False

    token = create_sign_up_token(user.id, db)
    link = f"{core_config.settings.ENDURAIN_HOST}/verify-email?token={token}"

    # Build localized email using the user's preferred language
    locale = core_i18n.normalize_locale(user.preferred_language)
    subject, html_content, text_content = sign_up_tokens_email_messages.get_signup_confirmation_email(
        user.name, link, core_config.settings.ENDURAIN_HOST, locale
    )
    return core_mail.send_email(mail, user.email, subject, html_content, text_content)


def send_sign_up_approval_request_email_to_admin(
    user_id: int, admin_user_id: int, mail: platform_providers.MailProvider, db: Session
) -> bool:
    """
    Email an admin that a new sign-up awaits approval.

    Args:
        user_id: ID of the user who signed up.
        admin_user_id: ID of the admin to email.
        mail: The platform mail provider.
        db: Active SQLAlchemy session.

    Returns:
        True if the email was handed to the mail server, False if it was skipped.

    Raises:
        MailError: On a transient delivery failure.
    """
    user = users_crud.get_user_by_id(user_id, db)
    admin = users_crud.get_user_by_id(admin_user_id, db)
    if not user or not admin:
        logger.debug(
            "Skipped sign-up approval request email: user or admin missing",
            extra=core_logger.context(user_id=user_id, admin_user_id=admin_user_id),
        )
        return False

    # Use the admin's preferred language
    locale = core_i18n.normalize_locale(admin.preferred_language)
    subject, html_content, text_content = sign_up_tokens_email_messages.get_admin_signup_notification_email(
        admin.name, user.name, user.username, core_config.settings.ENDURAIN_HOST, locale
    )
    return core_mail.send_email(mail, admin.email, subject, html_content, text_content)


def send_sign_up_approved_email_to_user(user_id: int, mail: platform_providers.MailProvider, db: Session) -> bool:
    """
    Email a user that their sign-up was approved.

    Args:
        user_id: ID of the approved user.
        mail: The platform mail provider.
        db: Active SQLAlchemy session.

    Returns:
        True if the email was handed to the mail server, False if it was skipped.

    Raises:
        MailError: On a transient delivery failure.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        logger.debug("Skipped sign-up approved email: user missing", extra=core_logger.context(user_id=user_id))
        return False

    # Build localized email using the approved user's preferred language
    locale = core_i18n.normalize_locale(user.preferred_language)
    subject, html_content, text_content = sign_up_tokens_email_messages.get_user_signup_approved_email(
        user.name, user.username, core_config.settings.ENDURAIN_HOST, locale
    )
    return core_mail.send_email(mail, user.email, subject, html_content, text_content)


def use_sign_up_token(token: str, db: Session) -> int:
    """
    Validate and consume a sign-up token.

    Args:
        token: Plaintext sign-up token to validate.
        db: Active SQLAlchemy session.

    Returns:
        The user ID associated with the token.

    Raises:
        HTTPException: 400 if the token is invalid or expired.
        HTTPException: 500 if an unexpected error occurs.
    """
    # Hash the provided token to find the database record
    token_hash = token_hashing.sha256_hex(token)

    # Look up the token in the database
    db_token = sign_up_tokens_crud.get_sign_up_token_by_hash(token_hash, db)

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired sign up token",
        )

    try:
        # Mark token as used
        sign_up_tokens_crud.mark_sign_up_token_used(db_token.id, db)

        # Return the associated user ID
        return db_token.user_id
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        logger.error(f"Error in use_sign_up_token: {err}", exc_info=err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_invalid_tokens_from_db() -> None:
    """
    Remove expired sign-up tokens from the database.

    Opens a new session, deletes expired tokens, and logs the count if any were
        removed.

    Returns:
        None
    """
    # Create a new database session using context manager
    with SessionLocal() as db:
        # Get num tokens deleted
        num_deleted = sign_up_tokens_crud.delete_expired_sign_up_tokens(db)

        # Log the number of deleted tokens
        if num_deleted > 0:
            logger.info(f"Deleted {num_deleted} expired sign up tokens", extra=core_logger.context(console=True))
