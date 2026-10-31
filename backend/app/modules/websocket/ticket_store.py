"""WebSocket authentication ticket store, backed by the platform state.

A ticket is a single-use, 30-second credential exchanged for the real access
token so the token never appears in a WebSocket URL. Storage goes through the
platform ``StateProvider`` (in-process under ``local``, Redis under
``distributed``), so this module no longer knows which backend is used.
"""

import secrets

from jasil.providers import StateBackendUnavailableError, StateProvider

import core.attempt_state as core_attempt_state
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

TICKET_TTL_SECONDS = 30


def _ticket_key(ticket: str) -> str:
    """Build the storage key of a ticket."""
    return core_attempt_state.key("websocket", "ticket", ticket)


class WsTicketStore:
    """Single-use, short-lived WebSocket auth tickets backed by the platform state.

    ``create_ticket`` uses an atomic set-if-absent so a token collision cannot
    overwrite another user's ticket; ``consume_ticket`` uses an atomic
    get-and-delete so a ticket is valid exactly once even under concurrency.

    Attributes:
        _state: The platform state provider the tickets live in.
    """

    def __init__(self, state: StateProvider) -> None:
        """Initialize the ticket store.

        Args:
            state: The platform state provider, resolved at the entry point.
        """
        self._state = state

    def create_ticket(self, user_id: int) -> str:
        """Issue a new short-lived ticket for a user.

        Args:
            user_id: Authenticated user ID.

        Returns:
            Opaque, URL-safe ticket string.

        Raises:
            core_attempt_state.StateUnavailableError: When storage is unavailable.
        """
        try:
            for _ in range(3):
                ticket = secrets.token_urlsafe(32)
                key = _ticket_key(ticket)
                if self._state.set_if_absent(key, str(user_id).encode(), ttl_seconds=TICKET_TTL_SECONDS):
                    return ticket
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("create_ticket", err)
        raise RuntimeError(  # pragma: no cover
            "Failed to generate a unique WS ticket after 3 attempts"
        )

    def consume_ticket(self, ticket: str) -> int | None:
        """Validate and consume a ticket (single-use).

        Args:
            ticket: Opaque ticket string from query parameter.

        Returns:
            Authenticated user ID, or None if invalid/expired/unknown.

        Raises:
            core_attempt_state.StateUnavailableError: When storage is unavailable.
        """
        key = _ticket_key(ticket)
        try:
            value = self._state.get_and_delete(key)
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("consume_ticket", err)
        if value is None:
            return None
        try:
            return int(value.decode())
        except (ValueError, TypeError):
            logger.warning("Unexpected non-integer value in WS ticket store")
            return None
