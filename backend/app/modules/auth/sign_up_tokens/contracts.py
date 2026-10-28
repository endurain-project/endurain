"""Internal data contracts for sign-up-token persistence."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SignUpTokenState(BaseModel):
    """Database state used by sign-up workflows."""

    id: str
    user_id: int
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used: bool

    model_config = ConfigDict(from_attributes=True, frozen=True)
