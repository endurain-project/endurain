from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime


class PasswordResetToken(BaseModel):
    id: str
    user_id: int
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used: bool

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str
