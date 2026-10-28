"""Internal data contracts for auth sessions."""

from datetime import datetime, timedelta
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class SessionTimeoutPolicy(Protocol):
    """Timeout values consumed by pure session validation."""

    idle_timeout: timedelta | None
    absolute_timeout: timedelta | None


class SessionRead(BaseModel):
    """Persisted session data used by authentication workflows."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: int
    refresh_token: str | None
    ip_address: str
    device_type: str
    operating_system: str
    operating_system_version: str
    browser: str
    browser_version: str
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    oauth_state_id: str | None
    tokens_exchanged: bool
    token_family_id: str
    rotation_count: int
    last_rotation_at: datetime | None
    csrf_token_hash: str | None
