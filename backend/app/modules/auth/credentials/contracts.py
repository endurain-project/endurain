"""Contracts for credential operations."""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class SupportsHashPassword(Protocol):
    """Structural protocol for objects that can hash a password."""

    def hash_password(self, password: str) -> str:
        """Implement the hash password operation."""
        ...


class SupportsVerifyPassword(Protocol):
    """Structural protocol for objects that can verify a password against a hash."""

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Implement the verify password operation."""
        ...


class CredentialRead(BaseModel):
    """Stored local credential data used by auth workflows."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    password_hash: str
    created_at: datetime
    updated_at: datetime
