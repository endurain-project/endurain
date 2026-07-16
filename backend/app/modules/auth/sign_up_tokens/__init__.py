"""
Sign-up tokens module for user registration.

This module provides CRUD operations, email messaging, and utilities for
sign-up token management.

Exports:
    - CRUD: create_sign_up_token,
      get_sign_up_token_by_hash,
      mark_sign_up_token_used,
      delete_expired_sign_up_tokens
    - Schemas: SignUpToken, SignUpConfirm,
      SignUpResponse
    - Models: SignUpToken (ORM model)
"""

from .crud import (
    create_sign_up_token,
    delete_expired_sign_up_tokens,
    get_sign_up_token_by_hash,
    mark_sign_up_token_used,
)
from .models import SignUpToken as SignUpTokenModel
from .schema import (
    SignUpConfirm,
    SignUpResponse,
    SignUpToken,
)

__all__ = [
    "SignUpConfirm",
    "SignUpResponse",
    # Pydantic schemas
    "SignUpToken",
    # Database model
    "SignUpTokenModel",
    # CRUD operations
    "create_sign_up_token",
    "delete_expired_sign_up_tokens",
    "get_sign_up_token_by_hash",
    "mark_sign_up_token_used",
]
