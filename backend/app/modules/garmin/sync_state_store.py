"""Shared state of a queued Garmin Connect gear or health sync.

The state is what ``GET /garminconnect/sync/{kind}`` reads back, and its claim keeps a user from
queueing the same kind twice. See :class:`core.attempt_state.SyncStateStore`.

Interface::

    begin(user_id, kind)                - queue a sync; False while one is still pending
    set_status(user_id, kind, status)   - record progress or the outcome
    get(user_id, kind)                  - read the current state, or None once expired
    close_pending(user_id, kind)        - fail a sync that is still pending
"""

from enum import StrEnum

from jasil.providers import StateProvider

import core.attempt_state as core_attempt_state
import modules.garmin.constants as garmin_constants
import modules.websocket.integration_service as websocket_integration


class GarminSyncStateStore(core_attempt_state.SyncStateStore):
    """Garmin sync state backed by the platform ``StateProvider``."""

    def __init__(self, state: StateProvider) -> None:
        """Initialize the sync state store.

        Args:
            state: The platform state provider.
        """
        super().__init__(state, "garmin", announce=self._announce_finished)

    @staticmethod
    def _announce_finished(user_id: int, kind: StrEnum) -> None:
        """Tell the user's client that a sync reached a final status.

        Args:
            user_id: The user whose sync ended.
            kind: What the sync pulled.
        """
        websocket_integration.push_job_changed(user_id, garmin_constants.job_name(garmin_constants.SyncKind(kind)))
