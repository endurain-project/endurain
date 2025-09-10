from pydantic import BaseModel, ConfigDict
from datetime import datetime


class SignUpToken(BaseModel):
    id: str
    user_id: int
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used: bool

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )


class SignUpConfirm(BaseModel):
    token: str
