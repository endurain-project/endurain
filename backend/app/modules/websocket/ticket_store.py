"""WebSocket authentication ticket store, backed by the platform state.

A ticket is a single-use, 30-second credential exchanged for the real access
token so the token never appears in a WebSocket URL. Storage goes through the
platform ``StateProvider`` (in-process under ``local``, Redis under
``distributed``), so this module no longer knows which backend is used.
"""

import secrets
from typing import NoReturn, Protocol, runtime_checkable

import core.logger as core_logger
import infra.runtime as platform_runtime
from infra.providers import StateBackendUnavailableError, StateProvider

TICKET_TTL_SECONDS = 30
_TICKET_KEY_PREFIX = "ws:ticket:"


class WsTicketStoreUnavailableError(RuntimeError):
    """
    Raised when WS ticket storage cannot be reached.

    Attributes:
        None.
    """


def _raise_store_unavailable(operation: str, err: StateBackendUnavailableError) -> NoReturn:
    """
    Log a storage outage and re-raise it as a WS-ticket error.

    Args:
        operation: Storage operation that failed.
        err: The provider outage error.

    Raises:
        WsTicketStoreUnavailableError: Always raised.
    """
    core_logger.print_to_log(f"WS ticket storage failed: {operation}", "error", exc=err)
    raise WsTicketStoreUnavailableError("WS ticket storage is unavailable") from err


@runtime_checkable
class WsTicketStoreProtocol(Protocol):
    """
    Contract for WS ticket stores.

    Attributes:
        None.
    """

    def create_ticket(self, user_id: int) -> str: ...

    def consume_ticket(self, ticket: str) -> int | None: ...


class WsTicketStore:
    """
    Single-use, short-lived WebSocket auth tickets backed by the platform state.

    ``create_ticket`` uses an atomic set-if-absent so a token collision cannot
    overwrite another user's ticket; ``consume_ticket`` uses an atomic
    get-and-delete so a ticket is valid exactly once even under concurrency.

    Attributes:
        _state_override: Explicit provider (tests); ``None`` resolves the
            process-wide provider lazily at call time.
    """

    def __init__(self, state: StateProvider | None = None) -> None:
        """
        Initialize the ticket store.

        Args:
            state: Optional explicit state provider (defaults to the process-wide one).
        """
        self._state_override = state

    @property
    def _state(self) -> StateProvider:
        return self._state_override if self._state_override is not None else platform_runtime.get_state()

    def create_ticket(self, user_id: int) -> str:
        """
        Issue a new short-lived ticket for a user.

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
        """
        Validate and consume a ticket (single-use).

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
            core_logger.print_to_log(
                "Unexpected non-integer value in WS ticket store",
                "warning",
            )
            return None


_ws_ticket_store = WsTicketStore()


def get_ws_ticket_store() -> WsTicketStore:
    """
    FastAPI dependency providing the singleton ticket store.

    Returns:
        The global WsTicketStore instance.
    """
    return _ws_ticket_store
