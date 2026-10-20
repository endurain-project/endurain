from functools import lru_cache

from fastapi import WebSocket

import core.logger as core_logger

logger = core_logger.get_logger(__name__)


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

        Args:
            user_id: The user's unique identifier.
            message: JSON-serializable data to send.
        """
        for websocket in self.get_connections(user_id):
            await websocket.send_json(message)

    async def broadcast(self, message: dict) -> None:
        """
        Send a JSON message to all connected users.

        Args:
            message: JSON-serializable data to broadcast.
        """
        for connections in list(self.active_connections.values()):
            for websocket in list(connections):
                await websocket.send_json(message)

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
