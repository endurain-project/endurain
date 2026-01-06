from functools import lru_cache

from fastapi import WebSocket

import core.logger as core_logger


class WebSocketManager:
    """
    Manage active WebSocket connections per user.

    Maintains a registry of authenticated WebSocket connections
    indexed by user ID, enabling message broadcasting and
    targeted notifications.

    Attributes:
        active_connections: Maps user IDs to their WebSocket.
    """

    def __init__(self) -> None:
        """Initialize the WebSocket manager with empty connections."""
        self.active_connections: dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        """
        Accept and register a new WebSocket connection.

        Args:
            user_id: The user's unique identifier.
            websocket: The WebSocket connection to register.
        """
        await websocket.accept()
        self.active_connections[user_id] = websocket
        core_logger.print_to_log(f"WebSocket connected for user {user_id}", "info")

    def disconnect(self, user_id: int) -> None:
        """
        Remove a user's WebSocket connection.

        Args:
            user_id: The user's unique identifier.
        """
        if self.active_connections.pop(user_id, None):
            core_logger.print_to_log(
                f"WebSocket disconnected for user {user_id}",
                "info",
            )

    async def send_message(self, user_id: int, message: dict) -> None:
        """
        Send a JSON message to a specific user.

        Args:
            user_id: The user's unique identifier.
            message: JSON-serializable data to send.
        """
        websocket = self.active_connections.get(user_id)
        if websocket:
            await websocket.send_json(message)

    async def broadcast(self, message: dict) -> None:
        """
        Send a JSON message to all connected users.

        Args:
            message: JSON-serializable data to broadcast.
        """
        for websocket in self.active_connections.values():
            await websocket.send_json(message)

    def get_connection(self, user_id: int) -> WebSocket | None:
        """
        Retrieve a user's WebSocket connection.

        Args:
            user_id: The user's unique identifier.

        Returns:
            The WebSocket connection or None if not found.
        """
        return self.active_connections.get(user_id)


@lru_cache(maxsize=1)
def get_websocket_manager() -> WebSocketManager:
    """
    Get the singleton WebSocket manager instance.

    Returns:
        The shared WebSocketManager instance.
    """
    return WebSocketManager()
