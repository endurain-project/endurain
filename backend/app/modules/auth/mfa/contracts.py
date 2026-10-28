"""Data transfer shapes for MFA persistence and integration operations."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class MFASecretStoreBackend(Protocol):
    """Temporary MFA setup-secret storage available to setup workflows."""

    def add_secret(self, user_id: int, secret: str) -> None: ...

    def get_secret(self, user_id: int) -> str | None: ...

    def delete_secret(self, user_id: int) -> None: ...


class MFAStateRead(BaseModel):
    """Internal MFA state returned by persistence operations."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    mfa_enabled: bool
    mfa_secret: str | None
