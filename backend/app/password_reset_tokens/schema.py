from pydantic import BaseModel, EmailStr
from datetime import datetime


class PasswordResetToken(BaseModel):
    id: str
    user_id: int
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used: bool

    model_config = {"from_attributes": True}


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str
