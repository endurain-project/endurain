"""Behavior published by the sign-up-token module to other packages."""

from sqlalchemy.orm import Session

import modules.auth.sign_up_tokens.service as sign_up_service


def revoke_pending_tokens(user_id: int, db: Session) -> None:
    """Stage invalidation of a user's unused verification tokens with the caller's pending user update."""
    sign_up_service.revoke_user_tokens(user_id, db)


def request_email_reverification(user_id: int, db: Session) -> bool:
    """Stage an email-verification event after a user's address changes."""
    return sign_up_service.request_email_reverification(user_id, db)


def request_sign_up_approved_email(user_id: int, db: Session) -> bool:
    """Stage an approval notice event with the caller's pending user update."""
    return sign_up_service.request_sign_up_approved_email(user_id, db)
