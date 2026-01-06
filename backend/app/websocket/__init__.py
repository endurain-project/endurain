"""WebSocket module for real-time notifications and communication."""

from websocket.manager import WebSocketManager, get_websocket_manager
from websocket.utils import notify_frontend

__all__ = [
    "WebSocketManager",
    "get_websocket_manager",
    "notify_frontend",
]
