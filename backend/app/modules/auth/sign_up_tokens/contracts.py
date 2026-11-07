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
    email: str | None
    previous_email: str | None

    model_config = ConfigDict(from_attributes=True, frozen=True)


class SignUpTokenClaim(BaseModel):
    """What a claimed token proves: its owner, the address it confirms and the address it replaces."""

    id: str
    user_id: int
    email: str | None
    previous_email: str | None

    model_config = ConfigDict(from_attributes=True, frozen=True)


class EmailChangeClaim(SignUpTokenClaim):
    """A claimed email-change token, which confirms ``email`` in place of ``previous_email``."""

    email: str
    previous_email: str


class PendingEmailChange(BaseModel):
    """An unconfirmed change of a user's email address."""

    email: str
    expires_at: datetime

    model_config = ConfigDict(frozen=True)
