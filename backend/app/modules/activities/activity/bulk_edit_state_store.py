"""Shared state of a queued bulk activity edit.

A bulk edit is accepted with 202 and runs on a worker, possibly on another replica. The state is what
``GET /activities/bulk-edit`` reads back, and its claim keeps a user from queueing the same edit twice.
See :class:`core.attempt_state.SyncStateStore`.

Interface::

    begin(user_id, kind)                - queue an edit; False while one is still pending
    set_status(user_id, kind, status)   - record progress or the outcome
    get(user_id, kind)                  - read the current state, or None once expired
    close_pending(user_id, kind)        - fail an edit that is still pending
"""

from jasil.providers import StateProvider

import core.attempt_state as core_attempt_state
import modules.activities.activity.bulk_edit_constants as bulk_edit_constants


class ActivityBulkEditStateStore(core_attempt_state.SyncStateStore):
    """Bulk edit state backed by the platform ``StateProvider``."""

    def __init__(
        self, state: StateProvider, ttl_seconds: int = bulk_edit_constants.BULK_EDIT_STATE_TTL_SECONDS
    ) -> None:
        """Initialize the bulk edit state store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long an edit's claim and state last.
        """
        super().__init__(state, "activities", ttl_seconds)
