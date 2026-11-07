"""Domain event channels owned by the password reset tokens module.

The payload carries the user id only: events are persisted, so neither the reset
token nor the email address may be put in one.
"""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published after a user asked for a password reset, so the reset email can be sent.
PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"  # noqa: S105 (event channel name, not a password)

# Published after a reset link set a new password, so the user can be told their password changed.
PASSWORD_RESET_COMPLETED = "auth.password_reset_completed"  # noqa: S105 (name matches the password-secret heuristic, not a secret)


class PasswordResetRequestedPayload(VersionedPayload):
    """Validated payload for the ``auth.password_reset_requested`` event.

    Attributes:
        user_id: The user who should receive the reset email.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int


class PasswordResetCompletedPayload(VersionedPayload):
    """Validated payload for the ``auth.password_reset_completed`` event.

    Attributes:
        user_id: The user whose password was reset.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
