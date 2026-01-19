from datetime import datetime, timedelta, timezone
from fastapi import (
    HTTPException,
    status,
)
from uuid import uuid4
import hashlib

from sqlalchemy.orm import Session

import sign_up_tokens.email_messages as sign_up_tokens_email_messages
import sign_up_tokens.schema as sign_up_tokens_schema
import sign_up_tokens.crud as sign_up_tokens_crud

import users.users.crud as users_crud
import users.users.models as users_models
import users.users.utils as users_utils

import core.apprise as core_apprise
import core.logger as core_logger

from core.database import SessionLocal


def create_sign_up_token(user_id: int, db: Session) -> str:
    # Generate token and hash
    token, token_hash = core_apprise.generate_token_and_hash()

    # Create token object
    reset_token = sign_up_tokens_schema.SignUpToken(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=token_hash,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc)
        + timedelta(hours=24),  # 24 hour expiration
        used=0,
    )

    # Save to database
    sign_up_tokens_crud.create_sign_up_token(reset_token, db)

    # Return the plain token (not the hash)
    return token


async def send_sign_up_email(
    user: users_models.Users, email_service: core_apprise.AppriseService, db: Session
) -> bool:
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

    # use default email message in English
    subject, html_content, text_content = (
        sign_up_tokens_email_messages.get_signup_confirmation_email_en(
            user.name, reset_link, email_service
        )
    )

    # Send email
    return await email_service.send_email(
        to_emails=[user.email],
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )


async def send_sign_up_admin_approval_email(
    user: users_models.Users, email_service: core_apprise.AppriseService, db: Session
) -> None:
    # Check if email service is configured
    if not email_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        )

    admins = users_utils.get_admin_users_or_404(db)

    # Send email to all admin users
    for admin in admins:
        # use default email message in English
        subject, html_content, text_content = (
            sign_up_tokens_email_messages.get_admin_signup_notification_email_en(
                admin.name, user.name, user.username, email_service
            )
        )

        # Send email
        await email_service.send_email(
            to_emails=[admin.email],
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )


async def send_sign_up_approval_email(
    user_id: int, email_service: core_apprise.AppriseService, db: Session
) -> bool:
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

    # use default email message in English
    subject, html_content, text_content = (
        sign_up_tokens_email_messages.get_user_signup_approved_email_en(
            user.name, user.username, email_service
        )
    )

    # Send email
    return await email_service.send_email(
        to_emails=[user.email],
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )


def use_sign_up_token(token: str, db: Session) -> int:
    # Hash the provided token to find the database record
    token_hash = hashlib.sha256(token.encode()).hexdigest()

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
        core_logger.print_to_log(f"Error in use_sign_up_token: {err}", "error", exc=err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_invalid_tokens_from_db():
    # Create a new database session using context manager
    with SessionLocal() as db:
        # Get num tokens deleted
        num_deleted = sign_up_tokens_crud.delete_expired_sign_up_tokens(db)

        # Log the number of deleted tokens
        if num_deleted > 0:
            core_logger.print_to_log_and_console(
                f"Deleted {num_deleted} expired sign up tokens", "info"
            )
