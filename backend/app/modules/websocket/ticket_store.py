"""WebSocket authentication ticket store, backed by the platform state.

A ticket is a single-use, 30-second credential exchanged for the real access
token so the token never appears in a WebSocket URL. Storage goes through the
platform ``StateProvider`` (in-process under ``local``, Redis under
``distributed``), so this module no longer knows which backend is used.
"""

import secrets
from typing import NoReturn

from jasil.providers import StateBackendUnavailableError, StateProvider

import core.exceptions as core_exceptions
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

TICKET_TTL_SECONDS = 30
_TICKET_KEY_PREFIX = "ws:ticket:"


class WsTicketStoreUnavailableError(core_exceptions.ServiceUnavailableError):
    """Raised when WS ticket storage cannot be reached; the API answers 503.

    Attributes:
        None.
    """


def _raise_store_unavailable(operation: str, err: StateBackendUnavailableError) -> NoReturn:
    """Log a storage outage and re-raise it as a WS-ticket error.

    Args:
        operation: Storage operation that failed.
        err: The provider outage error.

    Raises:
        WsTicketStoreUnavailableError: Always raised.
    """
    logger.error("WS ticket storage failed", exc_info=err, extra=core_logger.context(operation=operation))
    raise WsTicketStoreUnavailableError("WS ticket storage is unavailable") from err


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
            WsTicketStoreUnavailableError: When storage is unavailable.
        """
        try:
            for _ in range(3):
                ticket = secrets.token_urlsafe(32)
                key = f"{_TICKET_KEY_PREFIX}{ticket}"
                if self._state.set_if_absent(key, str(user_id).encode(), ttl_seconds=TICKET_TTL_SECONDS):
                    return ticket
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("create_ticket", err)
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
            WsTicketStoreUnavailableError: When storage is unavailable.
        """
        key = f"{_TICKET_KEY_PREFIX}{ticket}"
        try:
            value = self._state.get_and_delete(key)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("consume_ticket", err)
        if value is None:
            return None
        try:
            return int(value.decode())
        except (ValueError, TypeError):
            logger.warning("Unexpected non-integer value in WS ticket store")
            return None
