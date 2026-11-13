"""The process-local registry of open websocket connections, and bounded sends to them."""

import asyncio
import uuid
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

import core.logger as core_logger

logger = core_logger.get_logger(__name__)

# A client that stopped reading fills its socket buffer and ``send_json`` then
# waits forever; a send is a convenience, so give up rather than park the task.
SEND_TIMEOUT_SECONDS = 5.0

# One user cannot hold more sockets than a few tabs and devices need; past this the
# oldest is closed, so a script cannot grow the registry or a push's fan-out.
MAX_CONNECTIONS_PER_USER = 5

# Close code (private-use range) for a connection pushed out by a newer one. The client must
# not reconnect on it, or tabs past the cap would evict each other in a loop.
EVICTED_CLOSE_CODE = 4001

# Close code (private-use range) for a connection whose session was revoked or whose user was deactivated or
# deleted. The client must not reconnect on its own: a new ticket needs a valid session, so it would only be refused.
SESSION_ENDED_CLOSE_CODE = 4401


async def close_quietly(websocket: WebSocket, code: int, user_id: uuid.UUID) -> None:
    """Close a connection with a code, giving up on one that is stalled or already gone.

    Args:
        websocket: The connection to close.
        code: The close code to send.
        user_id: The connection's owner, named in the log context.
    """
    try:
        await asyncio.wait_for(websocket.close(code=code), timeout=SEND_TIMEOUT_SECONDS)
    except (TimeoutError, WebSocketDisconnect, RuntimeError) as err:
        logger.debug("WebSocket close failed", exc_info=err, extra=core_logger.context(user_id=user_id, code=code))


async def send_json_to_all(
    websockets: Sequence[WebSocket], message: dict[str, Any]
) -> list[tuple[WebSocket, BaseException]]:
    """Send a JSON message to several connections, isolating each one's failure.

    The sends run concurrently and each is bounded by ``SEND_TIMEOUT_SECONDS``, so a
    closed or stalled connection neither blocks nor hides the healthy ones.

    Args:
        websockets: The connections to send to.
        message: JSON-serializable data to send.

    Returns:
        Each connection that did not take the message with its failure (empty when all did).
    """
    results = await asyncio.gather(
        *(asyncio.wait_for(websocket.send_json(message), timeout=SEND_TIMEOUT_SECONDS) for websocket in websockets),
        return_exceptions=True,
    )
    return [
        (websocket, result)
        for websocket, result in zip(websockets, results, strict=True)
        if isinstance(result, BaseException)
    ]


class WebSocketManager:
    """Manage active WebSocket connections per user.

    Maintains a registry of authenticated WebSocket connections
    indexed by user ID, enabling message broadcasting and
    targeted notifications. A user can hold several connections
    at once (one per open tab or device), so a connection is
    removed by identity, never by user ID alone.

    Attributes:
        active_connections: Maps user IDs to their WebSockets, oldest first.
        session_ids: Maps each registered WebSocket to the session it was opened for.
    """

    def __init__(self) -> None:
        """Initialize the WebSocket manager with empty connections."""
        self.active_connections: dict[uuid.UUID, list[WebSocket]] = {}
        self.session_ids: dict[WebSocket, str] = {}

    async def connect(self, user_id: uuid.UUID, session_id: str, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection.

        Args:
            user_id: The user's unique identifier.
            session_id: The session the connection was opened for.
            websocket: The WebSocket connection to register.
        """
        await websocket.accept()
        self.session_ids[websocket] = session_id
        connections = self.active_connections.setdefault(user_id, [])
        connections.append(websocket)
        evicted = connections[:-MAX_CONNECTIONS_PER_USER]
        del connections[:-MAX_CONNECTIONS_PER_USER]
        for stale in evicted:
            self.session_ids.pop(stale, None)
            await close_quietly(stale, EVICTED_CLOSE_CODE, user_id)
        logger.debug("WebSocket connected", extra=core_logger.context(user_id=user_id))

    def disconnect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        """Remove one WebSocket connection of a user, leaving the others registered.

        Args:
            user_id: The user's unique identifier.
            websocket: The connection to remove.
        """
        connections = self.active_connections.get(user_id)
        if connections is None or websocket not in connections:
            return
        connections.remove(websocket)
        self.session_ids.pop(websocket, None)
        if not connections:
            del self.active_connections[user_id]
        logger.debug("WebSocket disconnected", extra=core_logger.context(user_id=user_id))

    def discard_failed(self, failures: Sequence[tuple[WebSocket, BaseException]]) -> None:
        """Unregister connections whose send failed at the transport.

        A stalled or closed connection would otherwise cost every later push another
        timeout. A payload that cannot be serialized says nothing about the connection,
        so it stays registered.

        Args:
            failures: Connection and failure pairs, as returned by ``send_json_to_all``.
        """
        for websocket, failure in failures:
            if isinstance(failure, TypeError | ValueError):
                continue
            for user_id, connections in list(self.active_connections.items()):
                if websocket in connections:
                    self.disconnect(user_id, websocket)

    def get_session_connections(
        self, user_id: uuid.UUID, session_id: str | None, except_session_id: str | None
    ) -> list[WebSocket]:
        """Retrieve the connections a session revocation ends.

        Args:
            user_id: The user whose sessions were revoked.
            session_id: The one revoked session, or None for every session of the user.
            except_session_id: With no ``session_id``, the session that was kept.

        Returns:
            A snapshot of the matching connections, empty if there are none.
        """
        return [
            websocket
            for websocket in self.active_connections.get(user_id, ())
            if (session_id is None or self.session_ids.get(websocket) == session_id)
            and (session_id is not None or self.session_ids.get(websocket) != except_session_id)
        ]

    def get_connections(self, user_id: uuid.UUID) -> list[WebSocket]:
        """Retrieve a user's WebSocket connections.

        Args:
            user_id: The user's unique identifier.

        Returns:
            A snapshot of the user's connections, empty if there are none.
        """
        return list(self.active_connections.get(user_id, ()))


@lru_cache(maxsize=1)
def get_websocket_manager() -> WebSocketManager:
    """Get the singleton WebSocket manager instance.

    Returns:
        The shared WebSocketManager instance.
    """
    return WebSocketManager()
