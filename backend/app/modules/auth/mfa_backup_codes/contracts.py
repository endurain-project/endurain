"""Persistence contracts for backup-code verification."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BackupCodeRead(BaseModel):
    """Stored backup-code fields required by security workflows."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    code_hash: str
    created_at: datetime
    used: bool
    expires_at: datetime | None
