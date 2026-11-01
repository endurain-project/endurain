"""Shared state of a queued account deletion.

A deletion is accepted with 202 and runs on a worker, possibly on another replica. The state is what
``GET /users/{user_id}/deletion`` reads back, and its claim keeps a user from being queued for deletion
twice. See :class:`core.attempt_state.SyncStateStore`.

Interface::

    begin(user_id, kind)                - queue a deletion; False while one is still pending
    set_status(user_id, kind, status)   - record progress or the outcome
    get(user_id, kind)                  - read the current state, or None once expired
    close_pending(user_id, kind)        - fail a deletion that is still pending
"""

from jasil.providers import StateProvider

import core.attempt_state as core_attempt_state
import modules.users.users.constants as users_constants


class UserDeletionStateStore(core_attempt_state.SyncStateStore):
    """Account deletion state backed by the platform ``StateProvider``."""

    def __init__(self, state: StateProvider, ttl_seconds: int = users_constants.DELETION_STATE_TTL_SECONDS) -> None:
        """Initialize the deletion state store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long a deletion's claim and state last.
        """
        super().__init__(state, "users", ttl_seconds)
