"""Data transfer shapes for MFA persistence and integration operations."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class MFASecretStoreBackend(Protocol):
    """Temporary MFA setup-secret storage available to setup workflows."""

    def add_secret(self, user_id: int, secret: str) -> None:
        """Store a pending MFA setup secret for a user."""
        ...

    def get_secret(self, user_id: int) -> str | None:
        """Return the pending MFA setup secret for a user."""
        ...

    def delete_secret(self, user_id: int) -> None:
        """Delete the pending MFA setup secret for a user."""
        ...


class SupportsClaimTotpStep(Protocol):
    """Records the TOTP time steps accepted for a user, so each works once."""

    def claim_totp_step(self, user_id: int, step: int) -> bool:
        """Record a step as used; False when it already was."""
        ...


class MFAStateRead(BaseModel):
    """Internal MFA state returned by persistence operations."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    mfa_enabled: bool
    mfa_secret: str | None
