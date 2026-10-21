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
from enum import StrEnum

import jasil.runtime as platform_runtime
from jasil.providers import StateBackendUnavailableError, StateProvider
from pydantic import BaseModel

import core.hashing as core_hashing
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

_LINK_STATE_KEY_PREFIX = "endurain:garmin:link:state"
# Must exceed the 65-second login timeout in garmin/utils.py, so a live attempt never expires
# under the poller. A dead replica's attempt expires after this, which also frees a retry.
_DEFAULT_TTL_SECONDS: int = 120


class LinkStatus(StrEnum):
    """Where a Garmin Connect link attempt is."""

    PENDING = "pending"
    MFA_REQUIRED = "mfa_required"
    COMPLETED = "completed"
    FAILED = "failed"


class LinkFailure(StrEnum):
    """Why a Garmin Connect link attempt failed, for the client to word."""

    INVALID_CREDENTIALS = "invalid_credentials"
    INCORRECT_MFA = "incorrect_mfa"
    TOO_MANY_REQUESTS = "too_many_requests"
    INTERNAL = "internal"


class LinkState(BaseModel):
    """The recorded state of one link attempt.

    Attributes:
        status: Where the attempt is.
        reason: Why it failed; set only when ``status`` is ``FAILED``.
    """

    status: LinkStatus
    reason: LinkFailure | None = None


_FINISHED = (LinkStatus.COMPLETED, LinkStatus.FAILED)


class GarminLinkStateStore:
    """
    Garmin link attempt state backed by the platform ``StateProvider``.

    Attributes:
        _state_override: Explicit provider (tests); ``None`` resolves the
            process-wide provider lazily at call time.
        _ttl_seconds: State lifetime in seconds.
    """

    def __init__(self, state: StateProvider | None = None, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        """
        Initialize the link state store.

        Args:
            state: Optional explicit state provider (defaults to the process-wide one).
            ttl_seconds: How long each state remains readable.
        """
        self._state_override = state
        self._ttl_seconds = ttl_seconds

    @property
    def _state(self) -> StateProvider:
        return self._state_override if self._state_override is not None else platform_runtime.get_state()

    def _key(self, user_id: int) -> str:
        """Build the storage key for a user's link attempt."""
        return f"{_LINK_STATE_KEY_PREFIX}:{core_hashing.sha256_hex(str(user_id))}"

    def _write(self, user_id: int, state: LinkState) -> None:
        self._state.set(self._key(user_id), state.model_dump_json().encode(), ttl_seconds=self._ttl_seconds)

    def begin(self, user_id: int) -> bool:
        """
        Start a link attempt unless one is still running.

        A finished attempt (completed or failed) is replaced, so the user can retry
        straight after a failure.

        Args:
            user_id: Authenticated user ID.

        Returns:
            True when the attempt was recorded as pending, False when another is in progress.

        Raises:
            StateBackendUnavailableError: When storage is unavailable.
        """
        pending = LinkState(status=LinkStatus.PENDING)
        if self._state.set_if_absent(self._key(user_id), pending.model_dump_json().encode(), self._ttl_seconds):
            return True
        current = self.get(user_id)
        if current is not None and current.status not in _FINISHED:
            return False
        self._write(user_id, pending)
        return True

    def set_status(self, user_id: int, status: LinkStatus, reason: LinkFailure | None = None) -> None:
        """
        Record a link attempt's progress or outcome.

        A failure to record is logged, not raised: the attempt itself must still finish, and
        the entry expires on its own.

        Args:
            user_id: Authenticated user ID.
            status: The new status.
            reason: Why the attempt failed, when ``status`` is ``FAILED``.
        """
        try:
            self._write(user_id, LinkState(status=status, reason=reason))
        except StateBackendUnavailableError as err:
            logger.warning("Failed to record the Garmin link state", exc_info=err)

    def get(self, user_id: int) -> LinkState | None:
        """
        Read a user's link attempt state.

        Args:
            user_id: Authenticated user ID.

        Returns:
            The state, or None when no attempt is recorded or it has expired.

        Raises:
            StateBackendUnavailableError: When storage is unavailable.
        """
        value = self._state.get(self._key(user_id))
        return LinkState(**json.loads(value)) if value is not None else None


garmin_link_state_store = GarminLinkStateStore()


def get_garmin_link_state_store() -> GarminLinkStateStore:
    """
    Return the module-level Garmin link state store instance.

    Returns:
        The global :data:`garmin_link_state_store` singleton.
    """
    return garmin_link_state_store
