"""Data transfer shapes for MFA persistence and integration operations."""

import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class MFASecretStoreBackend(Protocol):
    """Temporary MFA setup-secret storage available to setup workflows."""

    def add_secret(self, user_id: uuid.UUID, secret: str) -> None:
        """Store a pending MFA setup secret for a user."""
        ...

    def get_secret(self, user_id: uuid.UUID) -> str | None:
        """Return the pending MFA setup secret for a user."""
        ...

    def delete_secret(self, user_id: uuid.UUID) -> None:
        """Delete the pending MFA setup secret for a user."""
        ...


class SupportsClaimTotpStep(Protocol):
    """Records the TOTP time steps accepted for a user, so each works once."""

    def claim_totp_step(self, user_id: uuid.UUID, step: int) -> bool:
        """Record a step as used; False when it already was."""
        ...


class MFAFactorRead(BaseModel):
    """Internal enrolled-factor state returned by persistence operations."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    credential: str
