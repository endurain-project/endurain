"""Shared state of a profile import.

An import is accepted with 202 and runs on a worker, possibly on another replica. The state is
what ``GET /profile/import`` reads back, and its claim keeps a user from queueing two imports at
once. It lives in the platform ``StateProvider`` (see :mod:`core.attempt_state`).

Interface::

    begin(user_id)                          - queue an import; False while one is pending
    set_status(user_id, status, ...)        - record progress or the outcome
    get(user_id)                            - read the current state, or None once expired
"""

from jasil.providers import StateProvider
from pydantic import BaseModel

import core.attempt_state as core_attempt_state
import modules.users.users_profile.constants as profile_constants


class ProfileImportState(BaseModel):
    """The recorded state of one import.

    Attributes:
        status: Where the import is.
        failure: Why it failed; set only when ``status`` is ``FAILED``.
        imported: How many items of each kind were imported; set only when ``status`` is ``COMPLETED``.
    """

    status: profile_constants.ImportStatus
    failure: profile_constants.ImportFailure | None = None
    imported: dict[str, int] | None = None


_FINISHED = (profile_constants.ImportStatus.COMPLETED, profile_constants.ImportStatus.FAILED)


class ProfileImportStateStore:
    """Profile import state backed by the platform ``StateProvider``.

    Attributes:
        _attempts: The claim and state storage for imports.
    """

    def __init__(self, state: StateProvider, ttl_seconds: int = profile_constants.IMPORT_STATE_TTL_SECONDS) -> None:
        """Initialize the import state store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long an import's claim and state last.
        """
        self._attempts = core_attempt_state.AttemptStateStore(state, "users", "profile_import", ttl_seconds)

    def begin(self, user_id: int) -> bool:
        """Record an import as queued unless one is still pending.

        Args:
            user_id: The importing user.

        Returns:
            True when the import was recorded as queued, False when one is already pending.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        return self._attempts.begin(str(user_id), ProfileImportState(status=profile_constants.ImportStatus.QUEUED))

    def discard(self, user_id: int) -> None:
        """Forget an import that was refused before it started, so the user can try again at once.

        Args:
            user_id: The importing user.
        """
        self._attempts.discard(str(user_id))

    def set_status(
        self,
        user_id: int,
        status: profile_constants.ImportStatus,
        *,
        failure: profile_constants.ImportFailure | None = None,
        imported: dict[str, int] | None = None,
        strict: bool = False,
    ) -> None:
        """Record an import's progress or outcome.

        Args:
            user_id: The importing user.
            status: The new status.
            failure: Why the import failed, when ``status`` is ``FAILED``.
            imported: The counts of what was imported, when ``status`` is ``COMPLETED``.
            strict: Raise when the state cannot be recorded, instead of logging it.

        Raises:
            StateUnavailableError: When ``strict`` and storage is unavailable.
        """
        self._attempts.record(
            str(user_id),
            ProfileImportState(status=status, failure=failure, imported=imported),
            finished=status in _FINISHED,
            strict=strict,
        )

    def get(self, user_id: int) -> ProfileImportState | None:
        """Read a user's import state.

        Args:
            user_id: The importing user.

        Returns:
            The state, or None when none is recorded or it has expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        value = self._attempts.read(str(user_id))
        return ProfileImportState.model_validate_json(value) if value is not None else None
