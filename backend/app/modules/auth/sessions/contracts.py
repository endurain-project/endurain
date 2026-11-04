"""Internal data contracts for auth sessions."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class SessionTimeoutPolicy(Protocol):
    """Timeout values consumed by pure session validation."""

    @property
    def idle_timeout(self) -> timedelta | None:
        """Inactivity after which a session ends, or ``None`` when it never ends for inactivity."""
        ...

    @property
    def absolute_timeout(self) -> timedelta:
        """Age after which a session ends whatever its activity."""
        ...


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


class DeviceType(Enum):
    """Normalized device classes from a user-agent string."""

    MOBILE = "Mobile"
    TABLET = "Tablet"
    PC = "PC"


@dataclass
class DeviceInfo:
    """Parsed user-agent information."""

    device_type: DeviceType
    operating_system: str
    operating_system_version: str
    browser: str
    browser_version: str
