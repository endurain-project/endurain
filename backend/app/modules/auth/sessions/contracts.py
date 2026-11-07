"""Internal data contracts for auth sessions."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict

import modules.auth.schema as auth_schema


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


class SessionRevokeVerifier(Protocol):
    """Verifies the step-up of the administrator ending another user's sessions.

    The sessions package cannot verify a step-up itself: that lives in ``account_security``, and the action it
    authorises is named in ``identity_providers``, both of which depend on this package. The auth composition layer
    (``modules.auth.dependencies``) installs an implementation bound to the calling administrator and to the
    session-revoke action, and the service calls it before it deletes anything.
    """

    def __call__(self, step_up: auth_schema.StepUpVerification) -> None:
        """Verify the administrator's step-up.

        Args:
            step_up: The step-up verification the administrator sent.

        Raises:
            StepUpFailedError: When the verification fails.
            IdpReauthRequiredError: When the administrator has no password and sent no identity-provider proof.
            TooManyRequestsError: When the administrator is locked out of step-up.
        """
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
