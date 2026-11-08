"""Domain event channels owned by the password reset tokens module.

The requested payload carries the user id (``None`` for an address no account has) and the
requester's client address and user agent: events are persisted, so neither the reset token
nor the email address may be put in one.
"""

from collections.abc import Callable
from typing import Any, ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published after a user asked for a password reset, so the reset email can be sent.
PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"  # noqa: S105 (event channel name, not a password)

# Published after a reset link set a new password, so the user can be told their password changed.
PASSWORD_RESET_COMPLETED = "auth.password_reset_completed"  # noqa: S105 (name matches the password-secret heuristic, not a secret)


def _add_requester_client(payload: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a v1 requested payload, which named only the user, to v2 with no client data."""
    return {**payload, "ip_address": None, "user_agent": None}


class PasswordResetRequestedPayload(VersionedPayload):
    """Validated payload for the ``auth.password_reset_requested`` event.

    Attributes:
        user_id: The account registered for the requested address, or ``None`` when there is none.
        ip_address: The requester's client address, for the audit rows the worker writes.
        user_agent: The requester's ``User-Agent``, for the same rows.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 2
    UPGRADERS: ClassVar[dict[int, Callable[[dict[str, Any]], dict[str, Any]]]] = {1: _add_requester_client}

    user_id: int | None
    ip_address: str | None
    user_agent: str | None


class PasswordResetCompletedPayload(VersionedPayload):
    """Validated payload for the ``auth.password_reset_completed`` event.

    Attributes:
        user_id: The user whose password was reset.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
