"""WebSocket authentication ticket store, backed by the platform state.

A ticket is a single-use, 30-second credential exchanged for the real access
token so the token never appears in a WebSocket URL. Storage goes through the
platform ``StateProvider`` (in-process under ``local``, Redis under
``distributed``), so this module no longer knows which backend is used.
"""

import secrets
from dataclasses import dataclass

from jasil.providers import ClockProvider, StateBackendUnavailableError, StateProvider

import core.attempt_state as core_attempt_state
import core.hashing as core_hashing
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

TICKET_TTL_SECONDS = 30

#: Handshakes one client network may attempt within ``HANDSHAKE_WINDOW_SECONDS``. A browser that reconnects with
#: backoff makes a handful a minute per tab, so this leaves room for many tabs and for several people behind one
#: address, and stops a script from hammering the ticket lookup.
MAX_HANDSHAKES_PER_WINDOW = 60

#: Length of the fixed window handshakes are counted in. Windows are aligned to the clock and a counter belongs to
#: one window, so retrying never extends a refusal: the next window always starts at zero.
HANDSHAKE_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class WsTicketOwner:
    """Who a ticket was issued to.

    Attributes:
        user_id: The authenticated user.
        session_id: The session of the access token that asked for the ticket, so the socket ends with it.
    """

    user_id: int
    session_id: str


def _handshake_key(network: str, window: int) -> str:
    """Build the storage key of a client network's handshake counter in one window."""
    return core_attempt_state.key("websocket", "handshakes", f"{network}:{window}")


def _ticket_key(ticket: str) -> str:
    """Build the storage key of a ticket, keyed by its SHA-256 so the raw credential is never stored."""
    return core_attempt_state.key("websocket", "ticket", core_hashing.sha256_hex(ticket))


class WsTicketStore:
    """Single-use, short-lived WebSocket auth tickets backed by the platform state.

    ``create_ticket`` uses an atomic set-if-absent so a token collision cannot
    overwrite another user's ticket; ``consume_ticket`` uses an atomic
    get-and-delete so a ticket is valid exactly once even under concurrency.

    Attributes:
        _state: The platform state provider the tickets live in.
        _clock: The platform clock, which numbers the handshake windows.
    """

    def __init__(self, state: StateProvider, clock: ClockProvider) -> None:
        """Initialize the ticket store.

        Args:
            state: The platform state provider, resolved at the entry point.
            clock: The platform clock.
        """
        self._state = state
        self._clock = clock

    def allow_handshake(self, network: str) -> bool:
        """Count a handshake attempt and say whether its client network is still within the limit.

        The count lives in the platform state, so it holds across replicas. It is a fixed window: the window
        number is part of the key and the key expires after two windows, so a counter always ends and a
        network that keeps retrying is refused only until the window turns over.

        Args:
            network: The client network, as ``core.network.client_network`` returns it.

        Returns:
            False once the network made more than ``MAX_HANDSHAKES_PER_WINDOW`` attempts within the window.

        Raises:
            core_attempt_state.StateUnavailableError: When storage is unavailable.
        """
        try:
            window = int(self._clock.now().timestamp() // HANDSHAKE_WINDOW_SECONDS)
            attempts = self._state.incr(_handshake_key(network, window), ttl_seconds=2 * HANDSHAKE_WINDOW_SECONDS)
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("allow_handshake", err)
        return attempts <= MAX_HANDSHAKES_PER_WINDOW

    def create_ticket(self, user_id: int, session_id: str) -> str:
        """Issue a new short-lived ticket for a user's session.

        Args:
            user_id: Authenticated user ID.
            session_id: The session of the access token that asked for the ticket.

        Returns:
            Opaque, URL-safe ticket string.

        Raises:
            core_attempt_state.StateUnavailableError: When storage is unavailable.
        """
        try:
            for _ in range(3):
                ticket = secrets.token_urlsafe(32)
                key = _ticket_key(ticket)
                if self._state.set_if_absent(key, f"{user_id}:{session_id}".encode(), ttl_seconds=TICKET_TTL_SECONDS):
                    return ticket
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("create_ticket", err)
        raise RuntimeError(  # pragma: no cover
            "Failed to generate a unique WS ticket after 3 attempts"
        )

    def consume_ticket(self, ticket: str) -> WsTicketOwner | None:
        """Validate and consume a ticket (single-use).

        Args:
            ticket: Opaque ticket string from query parameter.

        Returns:
            The user and session the ticket was issued to, or None if invalid/expired/unknown.

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
        user_id, _, session_id = value.decode().partition(":")
        if not user_id.isascii() or not user_id.isdecimal() or not session_id:
            logger.warning("Unexpected value in WS ticket store")
            return None
        return WsTicketOwner(user_id=int(user_id), session_id=session_id)
