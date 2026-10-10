"""Utility functions for sign-up token operations."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

import core.apprise as core_apprise
import core.i18n as core_i18n
import core.logger as core_logger
import modules.auth.sign_up_tokens.crud as sign_up_tokens_crud
import modules.auth.sign_up_tokens.email_messages as sign_up_tokens_email_messages
import modules.auth.sign_up_tokens.schema as sign_up_tokens_schema
import modules.auth.token_hashing as token_hashing
import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema
import modules.users.users.utils as users_utils
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


def create_sign_up_token(user_id: int, db: Session) -> str:
    """
    Create and persist a sign-up token for a user.

    Args:
        user_id: ID of the user signing up.
        db: Active SQLAlchemy session.

    Returns:
        The plaintext token to deliver to the user.
        Only the hash is stored in the database.
    """
    # Generate token and hash
    token, token_hash = core_apprise.generate_token_and_hash()

    # Create token object
    reset_token = sign_up_tokens_schema.SignUpToken(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=token_hash,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=24),  # 24 hour expiration
        used=False,
    )

    # Save to database
    sign_up_tokens_crud.create_sign_up_token(reset_token, db)

    # Return the plain token (not the hash)
    return token


async def send_sign_up_email(
    user: users_schema.UsersRead,
    email_service: core_apprise.AppriseService,
    db: Session,
) -> bool:
    """
    Send a sign-up confirmation email to a user.

    Args:
        user: User model instance to email.
        email_service: Configured AppriseService.
        db: Active SQLAlchemy session.

    Returns:
        True if the email was sent successfully.

    Raises:
        HTTPException: 503 if the email service is not configured.
    """
    # Check if email service is configured
    if not email_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        )

    # Generate sign up token
    token = create_sign_up_token(user.id, db)

    # Generate reset link
    reset_link = f"{email_service.frontend_host}/verify-email?token={token}"

    # Build localized email using the user's preferred language
    locale = core_i18n.normalize_locale(user.preferred_language)
    subject, html_content, text_content = sign_up_tokens_email_messages.get_signup_confirmation_email(
        user.name, reset_link, email_service, locale
    )

    # Send email
    return await email_service.send_email(
        to_emails=[user.email],
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )


async def send_sign_up_admin_approval_email(
    user: users_schema.UsersRead,
    email_service: core_apprise.AppriseService,
    db: Session,
) -> None:
    """
    Notify admins about a new sign-up for approval.

    Args:
        user: User model instance who signed up.
        email_service: Configured AppriseService.
        db: Active SQLAlchemy session.

    Returns:
        None

    Raises:
        HTTPException: 503 if the email service is not configured.
    """
    # Check if email service is configured
    if not email_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        )

    admins = users_utils.get_admin_users_or_404(db)

    # Send email to all admin users
    for admin in admins:
        # Use the admin's preferred language for each notification
        locale = core_i18n.normalize_locale(admin.preferred_language)
        subject, html_content, text_content = sign_up_tokens_email_messages.get_admin_signup_notification_email(
            admin.name,
            user.name,
            user.username,
            email_service,
            locale,
        )

        # Send email
        await email_service.send_email(
            to_emails=[admin.email],
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )


async def send_sign_up_approval_email(
    user_id: int,
    email_service: core_apprise.AppriseService,
    db: Session,
) -> bool:
    """
    Send an approval notification email to a user.

    Args:
        user_id: ID of the approved user.
        email_service: Configured AppriseService.
        db: Active SQLAlchemy session.

    Returns:
        True if the email was sent successfully.

    Raises:
        HTTPException: 503 if the email service is not configured.
        HTTPException: 404 if user is not found.
    """
    # Check if email service is configured
    if not email_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        )

    # Get user info
    user = users_crud.get_user_by_id(user_id, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Build localized email using the approved user's preferred language
    locale = core_i18n.normalize_locale(user.preferred_language)
    subject, html_content, text_content = sign_up_tokens_email_messages.get_user_signup_approved_email(
        user.name, user.username, email_service, locale
    )

    # Send email
    return await email_service.send_email(
        to_emails=[user.email],
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )


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
