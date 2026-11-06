"""Shared state of a queued Strava link, gear sync or unlink.

The state is what ``GET /strava/sync/{kind}`` reads back, and its claim keeps a user from queueing
the same kind twice. See :class:`core.attempt_state.SyncStateStore`.

Interface::

    begin(user_id, kind)                - queue a sync; False while one is still pending
    set_status(user_id, kind, status)   - record progress or the outcome
    get(user_id, kind)                  - read the current state, or None once expired
    close_pending(user_id, kind)        - fail a sync that is still pending
"""

from enum import StrEnum

from jasil.providers import StateProvider

import core.attempt_state as core_attempt_state
import modules.strava.constants as strava_constants
import modules.websocket.integration_service as websocket_integration


class StravaSyncStateStore(core_attempt_state.SyncStateStore):
    """Strava sync state backed by the platform ``StateProvider``."""

    def __init__(self, state: StateProvider) -> None:
        """Initialize the sync state store.

        Args:
            state: The platform state provider.
        """
        super().__init__(state, "strava", announce=self._announce_finished)

    @staticmethod
    def _announce_finished(user_id: int, kind: StrEnum) -> None:
        """Tell the user's client that a link, gear sync or unlink reached a final status.

        Args:
            user_id: The user whose sync ended.
            kind: What the sync does.
        """
        websocket_integration.push_job_changed(user_id, strava_constants.job_name(strava_constants.SyncKind(kind)))
