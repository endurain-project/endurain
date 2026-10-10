"""
Password reset tokens module for user password recovery.

This module provides CRUD operations, email messaging, and utilities for
password reset token management.

Exports:
    - CRUD: create_password_reset_token,
      get_password_reset_token_by_hash,
      claim_password_reset_token,
      mark_password_reset_token_used,
      mark_user_password_reset_tokens_used,
      delete_expired_password_reset_tokens
    - Schemas: PasswordResetToken, PasswordResetRequest,
      PasswordResetConfirm, PasswordResetResponse
    - Models: PasswordResetToken (ORM model)
"""

from .crud import (
    claim_password_reset_token,
    create_password_reset_token,
    delete_expired_password_reset_tokens,
    get_password_reset_token_by_hash,
    mark_password_reset_token_used,
    mark_user_password_reset_tokens_used,
)
from .models import PasswordResetToken as PasswordResetTokenModel
from .schema import (
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetResponse,
    PasswordResetToken,
)

__all__ = [
    "PasswordResetConfirm",
    "PasswordResetRequest",
    "PasswordResetResponse",
    # Pydantic schemas
    "PasswordResetToken",
    # Database model
    "PasswordResetTokenModel",
    "claim_password_reset_token",
    # CRUD operations
    "create_password_reset_token",
    "delete_expired_password_reset_tokens",
    "get_password_reset_token_by_hash",
    "mark_password_reset_token_used",
    "mark_user_password_reset_tokens_used",
]
