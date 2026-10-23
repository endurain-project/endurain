"""Shared state of a Garmin Connect link attempt.

Linking logs in to Garmin in a background thread that may wait for an MFA code, while the
browser polls ``GET /garminconnect/link/status``. The poll can land on any replica, so the
state lives in the platform ``StateProvider`` (in-process under ``local``, Redis under
``distributed``) and nothing about it is process-local. The state is the contract: the
browser learns that an MFA code is wanted by reading it, never from a push that could be lost.

Interface::

    begin(user_id)                 - start an attempt; False while one is still running
    set_status(user_id, status)    - record progress or the outcome
    get(user_id)                   - read the current state, or None once expired
"""

import json

from jasil.providers import StateBackendUnavailableError, StateProvider
from pydantic import BaseModel

import core.hashing as core_hashing
import core.logger as core_logger
import modules.garmin.constants as garmin_constants

logger = core_logger.get_logger(__name__)

_LINK_STATE_KEY_PREFIX = "endurain:garmin:link:state"
_LINK_CLAIM_KEY_PREFIX = "endurain:garmin:link:claim"
# Must exceed the login timeout (MFA_WAIT_SECONDS plus the login itself), so a live attempt never expires
# under the poller. A dead replica's claim expires after this, which also frees a retry.
_DEFAULT_TTL_SECONDS: int = 120


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
        _state: The platform state provider.
        _ttl_seconds: State lifetime in seconds.
    """

    def __init__(self, state: StateProvider, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        """Initialize the link state store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long each state remains readable.
        """
        self._state = state
        self._ttl_seconds = ttl_seconds

    def _key(self, user_id: int) -> str:
        """Build the storage key for a user's link attempt."""
        return f"{_LINK_STATE_KEY_PREFIX}:{core_hashing.sha256_hex(str(user_id))}"

    def _claim_key(self, user_id: int) -> str:
        """Build the storage key of the claim that marks a user's attempt as running."""
        return f"{_LINK_CLAIM_KEY_PREFIX}:{core_hashing.sha256_hex(str(user_id))}"

    def _write(self, user_id: int, state: LinkState) -> None:
        self._state.set(self._key(user_id), state.model_dump_json().encode(), ttl_seconds=self._ttl_seconds)

    def begin(self, user_id: int) -> bool:
        """Start a link attempt unless one is still running.

        The claim is one atomic ``set_if_absent``, so two requests racing across replicas
        cannot both start a login. A finished attempt releases it, so the user can retry
        straight after a failure.

        Args:
            user_id: Authenticated user ID.

        Returns:
            True when the attempt was recorded as pending, False when another is in progress.

        Raises:
            StateBackendUnavailableError: When storage is unavailable.
        """
        if not self._state.set_if_absent(self._claim_key(user_id), b"1", self._ttl_seconds):
            return False
        self._write(user_id, LinkState(status=garmin_constants.LinkStatus.PENDING))
        return True

    def set_status(
        self, user_id: int, status: garmin_constants.LinkStatus, reason: garmin_constants.LinkFailure | None = None
    ) -> None:
        """Record a link attempt's progress or outcome.

        A finished attempt releases its claim. A failure to record is logged, not raised: the
        attempt itself must still finish, and the entries expire on their own.

        Args:
            user_id: Authenticated user ID.
            status: The new status.
            reason: Why the attempt failed, when ``status`` is ``FAILED``.
        """
        try:
            self._write(user_id, LinkState(status=status, reason=reason))
            if status in _FINISHED:
                self._state.delete(self._claim_key(user_id))
        except StateBackendUnavailableError as err:
            logger.warning("Failed to record the Garmin link state", exc_info=err)

    def get(self, user_id: int) -> LinkState | None:
        """Read a user's link attempt state.

        Args:
            user_id: Authenticated user ID.

        Returns:
            The state, or None when no attempt is recorded or it has expired.

        Raises:
            StateBackendUnavailableError: When storage is unavailable.
        """
        value = self._state.get(self._key(user_id))
        return LinkState(**json.loads(value)) if value is not None else None
