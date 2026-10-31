"""Shared state of a profile export.

An export is accepted with 202 and built on a worker, possibly on another replica. The state is
what ``GET /profile/export`` reads back, and its claim keeps a user from queueing two exports at
once. It lives in the platform ``StateProvider`` (see :mod:`core.attempt_state`).

Interface::

    begin(user_id)                          - queue an export; False while one is pending
    set_status(user_id, status, ...)        - record progress or the outcome
    get(user_id)                            - read the current state, or None once expired
"""

from jasil.providers import StateProvider
from pydantic import BaseModel

import core.attempt_state as core_attempt_state
import modules.users.users_profile.constants as profile_constants


class ProfileExportState(BaseModel):
    """The recorded state of one export.

    Attributes:
        status: Where the export is.
        failure: Why it failed; set only when ``status`` is ``FAILED``.
        size_bytes: Size of the staged archive; set only when ``status`` is ``COMPLETED``.
    """

    status: profile_constants.ExportStatus
    failure: profile_constants.ExportFailure | None = None
    size_bytes: int | None = None


_FINISHED = (profile_constants.ExportStatus.COMPLETED, profile_constants.ExportStatus.FAILED)


class ProfileExportStateStore:
    """Profile export state backed by the platform ``StateProvider``.

    Attributes:
        _attempts: The claim and state storage for exports.
    """

    def __init__(self, state: StateProvider, ttl_seconds: int = profile_constants.EXPORT_STATE_TTL_SECONDS) -> None:
        """Initialize the export state store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long an export's claim and state last.
        """
        self._attempts = core_attempt_state.AttemptStateStore(state, "users", "profile_export", ttl_seconds)

    def begin(self, user_id: int) -> bool:
        """Record an export as queued unless one is still pending.

        Args:
            user_id: The exporting user.

        Returns:
            True when the export was recorded as queued, False when one is already pending.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        return self._attempts.begin(str(user_id), ProfileExportState(status=profile_constants.ExportStatus.QUEUED))

    def set_status(
        self,
        user_id: int,
        status: profile_constants.ExportStatus,
        *,
        failure: profile_constants.ExportFailure | None = None,
        size_bytes: int | None = None,
    ) -> None:
        """Record an export's progress or outcome.

        Args:
            user_id: The exporting user.
            status: The new status.
            failure: Why the export failed, when ``status`` is ``FAILED``.
            size_bytes: The archive size, when ``status`` is ``COMPLETED``.
        """
        self._attempts.record(
            str(user_id),
            ProfileExportState(status=status, failure=failure, size_bytes=size_bytes),
            finished=status in _FINISHED,
        )

    def get(self, user_id: int) -> ProfileExportState | None:
        """Read a user's export state.

        Args:
            user_id: The exporting user.

        Returns:
            The state, or None when none is recorded or it has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        value = self._attempts.read(str(user_id))
        return ProfileExportState.model_validate_json(value) if value is not None else None
