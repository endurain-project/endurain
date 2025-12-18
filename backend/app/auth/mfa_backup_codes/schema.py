from pydantic import BaseModel, Field
from datetime import datetime


class MFABackupCodesResponse(BaseModel):
    codes: list[str] = Field(..., description="10 one-time backup codes")
    created_at: datetime


class MFABackupCodeStatus(BaseModel):
    has_codes: bool
    total: int
    unused: int
    used: int
    created_at: datetime | None = None
