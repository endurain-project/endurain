"""Shared state of a queued Garmin Connect gear or health sync.

A sync is accepted with 202 and runs on a worker, possibly on another replica. The state is
what ``GET /garminconnect/sync/{kind}`` reads back, and its claim keeps a user from queueing the
same kind of sync twice. It lives in the platform ``StateProvider`` (see
:mod:`modules.garmin.state_store`).

Interface::

    begin(user_id, kind)                - queue a sync; False while one is still pending
    set_status(user_id, kind, status)   - record progress or the outcome
    get(user_id, kind)                  - read the current state, or None once expired
"""

from jasil.providers import StateProvider
from pydantic import BaseModel

import modules.garmin.constants as garmin_constants
import modules.garmin.state_store as garmin_state_store


class SyncState(BaseModel):
    """The recorded state of one sync.

    Attributes:
        status: Where the sync is.
    """

    status: garmin_constants.SyncStatus


_FINISHED = (garmin_constants.SyncStatus.COMPLETED, garmin_constants.SyncStatus.FAILED)


def _subject(user_id: int, kind: garmin_constants.SyncKind) -> str:
    return f"{user_id}:{kind.value}"


class GarminSyncStateStore:
    """Garmin sync state backed by the platform ``StateProvider``.

    Attributes:
        _attempts: The claim and state storage for syncs.
    """

    def __init__(self, state: StateProvider, ttl_seconds: int = garmin_constants.SYNC_TTL_SECONDS) -> None:
        """Initialize the sync state store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long a sync's claim and state last.
        """
        self._attempts = garmin_state_store.AttemptStateStore(state, "sync", ttl_seconds)

    def begin(self, user_id: int, kind: garmin_constants.SyncKind) -> bool:
        """Record a sync as queued unless one of this kind is still pending.

        Args:
            user_id: The user to sync.
            kind: What the sync pulls.

        Returns:
            True when the sync was recorded as queued, False when one is already pending.

        Raises:
            GarminStateUnavailableError: When storage is unavailable.
        """
        return self._attempts.begin(_subject(user_id, kind), SyncState(status=garmin_constants.SyncStatus.QUEUED))

    def set_status(self, user_id: int, kind: garmin_constants.SyncKind, status: garmin_constants.SyncStatus) -> None:
        """Record a sync's progress or outcome.

        Args:
            user_id: The user being synced.
            kind: What the sync pulls.
            status: The new status.
        """
        self._attempts.record(_subject(user_id, kind), SyncState(status=status), finished=status in _FINISHED)

    def get(self, user_id: int, kind: garmin_constants.SyncKind) -> SyncState | None:
        """Read a sync's state.

        Args:
            user_id: The user being synced.
            kind: What the sync pulls.

        Returns:
            The state, or None when none is recorded or it has expired.

        Raises:
            GarminStateUnavailableError: When storage is unavailable.
        """
        value = self._attempts.read(_subject(user_id, kind))
        return SyncState.model_validate_json(value) if value is not None else None
