import asyncio
from collections.abc import Sequence
from functools import lru_cache

from fastapi import WebSocket

import core.logger as core_logger

logger = core_logger.get_logger(__name__)

# A client that stopped reading fills its socket buffer and ``send_json`` then
# waits forever; a send is a convenience, so give up rather than park the task.
SEND_TIMEOUT_SECONDS = 5.0


async def send_json_to_all(websockets: Sequence[WebSocket], message: dict) -> list[BaseException]:
    """
    Send a JSON message to several connections, isolating each one's failure.

    The sends run concurrently and each is bounded by ``SEND_TIMEOUT_SECONDS``, so a
    closed or stalled connection neither blocks nor hides the healthy ones.

    Args:
        websockets: The connections to send to.
        message: JSON-serializable data to send.

    Returns:
        The failure of each connection that did not take the message (empty when all did).
    """
    results = await asyncio.gather(
        *(asyncio.wait_for(websocket.send_json(message), timeout=SEND_TIMEOUT_SECONDS) for websocket in websockets),
        return_exceptions=True,
    )
    return [result for result in results if isinstance(result, BaseException)]


class WebSocketManager:
    """
    Manage active WebSocket connections per user.

    Maintains a registry of authenticated WebSocket connections
    indexed by user ID, enabling message broadcasting and
    targeted notifications. A user can hold several connections
    at once (one per open tab or device), so a connection is
    removed by identity, never by user ID alone.

    Attributes:
        active_connections: Maps user IDs to their WebSockets, oldest first.
    """

    def __init__(self) -> None:
        """Initialize the WebSocket manager with empty connections."""
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        """
        Accept and register a new WebSocket connection.

        Args:
            user_id: The user's unique identifier.
            websocket: The WebSocket connection to register.
        """
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)
        logger.debug(f"WebSocket connected for user {user_id}")

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        """
        Remove one WebSocket connection of a user, leaving the others registered.

        Args:
            user_id: The user's unique identifier.
            websocket: The connection to remove.
        """
        connections = self.active_connections.get(user_id)
        if connections is None or websocket not in connections:
            return
        connections.remove(websocket)
        if not connections:
            del self.active_connections[user_id]
        logger.debug(f"WebSocket disconnected for user {user_id}")

    async def send_message(self, user_id: int, message: dict) -> None:
        """
        Send a JSON message to every connection of a specific user.

        A connection that fails is logged and skipped; the others still receive it.

        Args:
            user_id: The user's unique identifier.
            message: JSON-serializable data to send.
        """
        failures = await send_json_to_all(self.get_connections(user_id), message)
        for failure in failures:
            logger.debug(f"WebSocket send failed for user {user_id}", exc_info=failure)

    async def broadcast(self, message: dict) -> None:
        """
        Send a JSON message to all connected users, skipping connections that fail.

        Args:
            message: JSON-serializable data to broadcast.
        """
        websockets = [websocket for connections in self.active_connections.values() for websocket in connections]
        for failure in await send_json_to_all(websockets, message):
            logger.debug("WebSocket broadcast send failed", exc_info=failure)

    def get_connections(self, user_id: int) -> list[WebSocket]:
        """
        Retrieve a user's WebSocket connections.

        Args:
            user_id: The user's unique identifier.

        Returns:
            A snapshot of the user's connections, empty if there are none.
        """
        return list(self.active_connections.get(user_id, ()))


@lru_cache(maxsize=1)
def get_websocket_manager() -> WebSocketManager:
    """
    Get the singleton WebSocket manager instance.

    Returns:
        The shared WebSocketManager instance.
    """
    return WebSocketManager()
