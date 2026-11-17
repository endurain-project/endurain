"""Shared state of a queued Strava link, gear sync or unlink.

The state is what ``GET /jobs/{job_id}`` reads back, and its claim keeps a user from queueing
the same kind twice. See :class:`core.attempt_state.SyncStateStore`.

Interface::

    begin(user_id, kind, conflict=...)  - queue a sync; raises while one is still pending
    set_status(user_id, kind, status)   - record progress or the outcome
    get(user_id, kind)                  - read the current state, or None once expired
    read_job(job)                       - read the sync a job reference names
    close_pending(user_id, kind)        - fail a sync that is still pending
"""

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
        super().__init__(
            state,
            "strava",
            job_kind=lambda kind: strava_constants.job_kind(strava_constants.SyncKind(kind)),
            announce=websocket_integration.announce_job,
        )
