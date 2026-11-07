"""Internal data contracts for password-reset-token persistence."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PasswordResetTokenState(BaseModel):
    """Database state used by password reset workflows."""

    id: str
    user_id: int
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used: bool

    model_config = ConfigDict(from_attributes=True, frozen=True)
