"""Behavior published by the password-reset-token module to other packages."""

import uuid

from sqlalchemy.orm import Session

import modules.auth.password_reset_tokens.crud as password_reset_crud


def revoke_unused_tokens(user_id: uuid.UUID, db: Session) -> None:
    """Stage invalidation of a user's unused reset tokens with the caller's pending password or email change."""
    password_reset_crud.mark_user_password_reset_tokens_used(user_id, db)
