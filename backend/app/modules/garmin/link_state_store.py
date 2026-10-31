"""Shared state of a Garmin Connect link attempt.

Linking logs in to Garmin in a background thread that may wait for an MFA code, while the
browser polls ``GET /garminconnect/link/status``. The poll can land on any replica, so the
state lives in the platform ``StateProvider`` (see :mod:`core.attempt_state`). The state
is the contract: the browser learns that an MFA code is wanted by reading it, never from a push
that could be lost.

Interface::

    begin(user_id)                 - start an attempt; False while one is still running
    set_status(user_id, status)    - record progress or the outcome
    get(user_id)                   - read the current state, or None once expired
"""

from jasil.providers import StateProvider
from pydantic import BaseModel

import core.attempt_state as core_attempt_state
import modules.garmin.constants as garmin_constants


class LinkState(BaseModel):
    """The recorded state of one link attempt.

    Attributes:
        status: Where the attempt is.
        reason: Why it failed; set only when ``status`` is ``FAILED``.
    """

    status: garmin_constants.LinkStatus
    reason: garmin_constants.LinkFailure | None = None


_FINISHED = (garmin_constants.LinkStatus.COMPLETED, garmin_constants.LinkStatus.FAILED)


class GarminLinkStateStore:
    """Garmin link attempt state backed by the platform ``StateProvider``.

    Attributes:
        _attempts: The claim and state storage for link attempts.
    """

    def __init__(self, state: StateProvider, ttl_seconds: int = garmin_constants.LINK_TTL_SECONDS) -> None:
        """Initialize the link state store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long a link attempt's claim and state last.
        """
        self._attempts = core_attempt_state.AttemptStateStore(state, "garmin", "link", ttl_seconds)

    def begin(self, user_id: int) -> bool:
        """Start a link attempt unless one is still running.

        A finished attempt releases the claim, so the user can retry straight after a failure.

        Args:
            user_id: Authenticated user ID.

        Returns:
            True when the attempt was recorded as pending, False when another is in progress.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        return self._attempts.begin(str(user_id), LinkState(status=garmin_constants.LinkStatus.PENDING))

    def release(self, user_id: int) -> None:
        """Abandon an attempt that never got to run, so the user can retry at once.

        Args:
            user_id: Authenticated user ID.
        """
        self._attempts.release(str(user_id))

    def set_status(
        self, user_id: int, status: garmin_constants.LinkStatus, reason: garmin_constants.LinkFailure | None = None
    ) -> None:
        """Record a link attempt's progress or outcome.

        Args:
            user_id: Authenticated user ID.
            status: The new status.
            reason: Why the attempt failed, when ``status`` is ``FAILED``.
        """
        self._attempts.record(str(user_id), LinkState(status=status, reason=reason), finished=status in _FINISHED)

    def get(self, user_id: int) -> LinkState | None:
        """Read a user's link attempt state.

        Args:
            user_id: Authenticated user ID.

        Returns:
            The state, or None when no attempt is recorded or it has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        value = self._attempts.read(str(user_id))
        return LinkState.model_validate_json(value) if value is not None else None
